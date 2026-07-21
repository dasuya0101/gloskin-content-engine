#!/usr/bin/env python3
"""
llm_router.py — multi-model routing for copy tasks
==================================================
Repetitive copy work (hook variants, captions, brief JSON) is cheap-model work.
This routes each named task to a configured model/provider so you can push bulk
copy to low-tier models (Kimi, DeepSeek, GLM via OpenRouter) and keep premium
models for the few things that need them — mirroring your OpenClaw setup.

Providers supported via API (NOT consumer subscriptions): openrouter, anthropic, openai.
Set the matching key:
  export OPENROUTER_API_KEY=...   # cheap routing to Kimi/DeepSeek/GLM/etc
  export ANTHROPIC_API_KEY=...
  export OPENAI_API_KEY=...

Edit ROUTES to map task -> (provider, model). One place to retune cost vs quality.

NOTE on images: image generation does NOT go through here and must use a real
image API (gpt-image-1) or Dreamina credits. Driving a consumer ChatGPT/Dreamina
*subscription* via a browser agent violates their ToS and risks bans — not supported.
"""
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

# task name -> (provider, model). Tune freely.
ROUTES = {
    "copy_brief":    ("openrouter", "moonshotai/kimi-k2"),      # bulk brief JSON
    "hook_variants": ("openrouter", "deepseek/deepseek-chat"),  # cheap, high volume
    "caption":       ("openrouter", "deepseek/deepseek-chat"),
    "reddit_longform": ("openrouter", "deepseek/deepseek-chat"),
    "x_thread":      ("openrouter", "deepseek/deepseek-chat"),
    "tiktok_script": ("openrouter", "deepseek/deepseek-chat"),
    "compliance_lint": ("openrouter", "openai/gpt-4.1-mini"),
    "analysis":      ("anthropic", "claude-sonnet-4-5"),        # winner analysis = premium
}
DEFAULT_ROUTE = ("anthropic", "claude-sonnet-4-5")


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


def _required_env(name):
    _load_dotenv()
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _with_retries(call, provider, model, attempts=3):
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception:
            if attempt == attempts:
                raise
            print(
                f"[{provider}] {model} request failed; retrying "
                f"({attempt + 1}/{attempts})",
                file=sys.stderr,
            )
            time.sleep(attempt)


def complete(system, user, task="copy_brief", max_tokens=900, temperature=None):
    provider, model = ROUTES.get(task, DEFAULT_ROUTE)
    if provider == "openrouter":
        return _openrouter(system, user, model, max_tokens, temperature)
    if provider == "anthropic":
        return _anthropic(system, user, model, max_tokens, temperature)
    if provider == "openai":
        return _openai(system, user, model, max_tokens, temperature)
    raise ValueError(f"unknown provider {provider}")


def _openrouter(system, user, model, max_tokens, temperature=None):
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if temperature is not None:
        body["temperature"] = temperature
    payload = json.dumps(body).encode("utf-8")
    request = Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {_required_env('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    def send():
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    data = _with_retries(
        send,
        "openrouter",
        model,
    )
    usage = data.get("usage") or {}
    if usage:
        safe_usage = {
            key: usage[key]
            for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost")
            if key in usage
        }
        print(f"[usage] openrouter {model} {json.dumps(safe_usage)}", file=sys.stderr)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("OpenRouter response did not contain message content") from exc


def _anthropic(system, user, model, max_tokens, temperature=None):
    import anthropic
    client = anthropic.Anthropic()
    kwargs = {"model": model, "max_tokens": max_tokens, "system": system,
              "messages": [{"role": "user", "content": user}]}
    if temperature is not None:
        kwargs["temperature"] = temperature
    m = client.messages.create(**kwargs)
    return "".join(b.text for b in m.content if b.type == "text")


def _openai(system, user, model, max_tokens, temperature=None):
    from openai import OpenAI
    client = OpenAI()
    kwargs = {"model": model, "max_tokens": max_tokens,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]}
    if temperature is not None:
        kwargs["temperature"] = temperature
    r = client.chat.completions.create(**kwargs)
    return r.choices[0].message.content
