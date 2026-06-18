#!/usr/bin/env python3
"""
image_router.py — pluggable image generation
=============================================
Abstracts face/image generation behind a provider registry so you can swap in
whatever image API you want without touching character_factory. Returns raw PNG
bytes from every provider.

Select provider with env IMAGE_PROVIDER (default "openai"):
  export IMAGE_PROVIDER=openai      # gpt-image-1 (generate + edit)
  export IMAGE_PROVIDER=custom      # your own HTTP image API (template below)

Add a new provider in one place:
  image_router.register("myprovider", generate=my_gen, edit=my_edit)
where my_gen(prompt, size, **kw) -> PNG bytes, and my_edit(image_bytes, prompt,
size, **kw) -> PNG bytes (edit optional; omit if the API can't do it).

NOTE: providers here are real HTTP/SDK APIs. Driving a consumer ChatGPT/Dreamina
*subscription* via browser automation is out of scope by design.
"""
import base64
import os

_PROVIDERS = {}


def register(name, generate=None, edit=None):
    _PROVIDERS[name] = {"generate": generate, "edit": edit}


def _active():
    name = os.environ.get("IMAGE_PROVIDER", "openai")
    if name not in _PROVIDERS:
        raise ValueError(f"image provider '{name}' not registered. "
                         f"Available: {list(_PROVIDERS)}")
    return name, _PROVIDERS[name]


def generate(prompt, size="1024x1536", **kw):
    name, p = _active()
    if not p["generate"]:
        raise NotImplementedError(f"provider '{name}' has no generate()")
    return p["generate"](prompt, size, **kw)


def edit(image_bytes, prompt, size="1024x1536", **kw):
    """Edit an existing image (used for before->after consistency). Falls back to
    generate() if the active provider can't edit."""
    name, p = _active()
    if p["edit"]:
        return p["edit"](image_bytes, prompt, size, **kw)
    # graceful fallback: regenerate from prompt (less consistent — provider warns)
    return generate(prompt, size, **kw)


# ---------------------------------------------------------------------------
# Built-in provider: OpenAI gpt-image-1
# ---------------------------------------------------------------------------
def _openai_generate(prompt, size, quality="high", **kw):
    from openai import OpenAI
    client = OpenAI()
    r = client.images.generate(model="gpt-image-1", prompt=prompt,
                               size=size, quality=quality)
    return base64.b64decode(r.data[0].b64_json)


def _openai_edit(image_bytes, prompt, size, **kw):
    import io
    from openai import OpenAI
    client = OpenAI()
    buf = io.BytesIO(image_bytes)
    buf.name = "in.png"
    r = client.images.edit(model="gpt-image-1", image=buf, prompt=prompt, size=size)
    return base64.b64decode(r.data[0].b64_json)


register("openai", generate=_openai_generate, edit=_openai_edit)


# ---------------------------------------------------------------------------
# Template provider: any HTTP image API  (copy + adapt, then IMAGE_PROVIDER=custom)
# Fill in the endpoint/payload/response shape for your chosen API.
# ---------------------------------------------------------------------------
def _custom_generate(prompt, size, **kw):
    import requests  # pip install requests
    endpoint = os.environ["IMAGE_API_URL"]          # e.g. https://api.yourprovider.com/v1/images
    key = os.environ.get("IMAGE_API_KEY", "")
    w, h = size.split("x")
    resp = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {key}"},
        json={"prompt": prompt, "width": int(w), "height": int(h)},  # adapt to your API
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    # adapt these two lines to your API's response shape:
    if "b64" in data:
        return base64.b64decode(data["b64"])
    if "url" in data:
        return requests.get(data["url"], timeout=60).content
    raise ValueError("custom provider: unrecognized response shape — edit _custom_generate")


# edit omitted for the template -> image_router.edit() will fall back to generate()
register("custom", generate=_custom_generate, edit=None)
