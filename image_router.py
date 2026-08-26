#!/usr/bin/env python3
"""Pluggable image generation for direct HTTP/SDK providers.

Codex subscription generation is deliberately handled by image_queue.py. A
local Flask process cannot invoke the signed-in Codex image tool directly.
"""
import base64
import os
from pathlib import Path


_PROVIDERS = {}


def _load_dotenv():
    path = Path(__file__).resolve().with_name(".env")
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key and value:
            os.environ.setdefault(key, value)


def register(name, generate=None, edit=None, *, label=None, required_env=(),
             edit_required_env=(), notes=""):
    _PROVIDERS[name] = {
        "generate": generate,
        "edit": edit,
        "label": label or name,
        "required_env": tuple(required_env),
        "edit_required_env": tuple(edit_required_env),
        "notes": notes,
    }


def _active(provider=None):
    _load_dotenv()
    name = provider or os.environ.get("IMAGE_PROVIDER", "openai")
    if name not in _PROVIDERS:
        raise ValueError(
            f"image provider '{name}' not registered. Available: {list(_PROVIDERS)}")
    return name, _PROVIDERS[name]


def list_providers():
    """Return capabilities and missing env names without exposing secret values."""
    _load_dotenv()
    rows = []
    for name, provider in _PROVIDERS.items():
        missing = [key for key in provider["required_env"] if not os.environ.get(key)]
        missing_edit = [
            key for key in provider["edit_required_env"] if not os.environ.get(key)]
        rows.append({
            "id": name,
            "label": provider["label"],
            "mode": "api",
            "can_generate": bool(provider["generate"]),
            "can_edit": bool(provider["edit"]) and not missing_edit,
            "configured": not missing,
            "missing_env": missing,
            "missing_edit_env": missing_edit,
            "notes": provider["notes"],
        })
    return rows


def generate(prompt, size="1024x1536", provider=None, **kwargs):
    name, selected = _active(provider)
    if not selected["generate"]:
        raise NotImplementedError(f"provider '{name}' has no generate()")
    return selected["generate"](prompt, size, **kwargs)


def edit(image_bytes, prompt, size="1024x1536", provider=None,
         allow_generate_fallback=True, **kwargs):
    """Edit an image, optionally falling back to identity-unsafe generation."""
    name, selected = _active(provider)
    if selected["edit"]:
        return selected["edit"](image_bytes, prompt, size, **kwargs)
    if not allow_generate_fallback:
        raise NotImplementedError(f"provider '{name}' cannot edit reference images")
    return generate(prompt, size, provider=name, **kwargs)


def _openai_generate(prompt, size, quality="high", **kwargs):
    from openai import OpenAI
    client = OpenAI()
    response = client.images.generate(
        model=os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1"),
        prompt=prompt,
        size=size,
        quality=quality,
    )
    return base64.b64decode(response.data[0].b64_json)


def _openai_edit(image_bytes, prompt, size, **kwargs):
    import io
    from openai import OpenAI
    client = OpenAI()
    buffer = io.BytesIO(image_bytes)
    buffer.name = "in.png"
    response = client.images.edit(
        model=os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1"),
        image=buffer,
        prompt=prompt,
        size=size,
    )
    return base64.b64decode(response.data[0].b64_json)


register(
    "openai",
    generate=_openai_generate,
    edit=_openai_edit,
    label="OpenAI GPT Image API",
    required_env=("OPENAI_API_KEY",),
    notes="Direct API billing; supports identity-preserving reference edits.",
)


def _custom_headers():
    key = os.environ.get("IMAGE_API_KEY", "")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _custom_response_bytes(response, requests):
    response.raise_for_status()
    if response.headers.get("content-type", "").startswith("image/"):
        return response.content
    data = response.json()
    candidates = [data]
    if isinstance(data.get("data"), list) and data["data"]:
        candidates.append(data["data"][0])
    if isinstance(data.get("output"), dict):
        candidates.append(data["output"])
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        encoded = candidate.get("b64") or candidate.get("b64_json")
        if encoded:
            return base64.b64decode(encoded)
        url = candidate.get("url") or candidate.get("image_url")
        if url:
            image_response = requests.get(url, timeout=60)
            image_response.raise_for_status()
            return image_response.content
    raise ValueError("custom provider returned no b64 or image URL")


def _custom_payload(prompt, size):
    width, height = size.split("x")
    payload = {"prompt": prompt, "width": int(width), "height": int(height)}
    if os.environ.get("IMAGE_API_MODEL"):
        payload["model"] = os.environ["IMAGE_API_MODEL"]
    return payload


def _custom_generate(prompt, size, **kwargs):
    import requests
    response = requests.post(
        os.environ["IMAGE_API_URL"],
        headers=_custom_headers(),
        json=_custom_payload(prompt, size),
        timeout=120,
    )
    return _custom_response_bytes(response, requests)


def _custom_edit(image_bytes, prompt, size, **kwargs):
    import requests
    endpoint = os.environ.get("IMAGE_API_EDIT_URL")
    if not endpoint:
        raise NotImplementedError("custom image edits require IMAGE_API_EDIT_URL")
    payload = _custom_payload(prompt, size)
    payload["image_b64"] = base64.b64encode(image_bytes).decode("ascii")
    response = requests.post(
        endpoint,
        headers=_custom_headers(),
        json=payload,
        timeout=180,
    )
    return _custom_response_bytes(response, requests)


register(
    "custom",
    generate=_custom_generate,
    edit=_custom_edit,
    label="Custom image API",
    required_env=("IMAGE_API_URL",),
    edit_required_env=("IMAGE_API_EDIT_URL",),
    notes=(
        "Generic synchronous JSON adapter. Configure IMAGE_API_EDIT_URL for reference edits; "
        "Dreamina or Kling need a provider-specific adapter if their endpoint contract differs."
    ),
)
