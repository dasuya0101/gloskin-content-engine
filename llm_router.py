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
import os

# task name -> (provider, model). Tune freely.
ROUTES = {
    "copy_brief":    ("openrouter", "moonshotai/kimi-k2"),      # bulk brief JSON
    "hook_variants": ("openrouter", "deepseek/deepseek-chat"),  # cheap, high volume
    "caption":       ("openrouter", "deepseek/deepseek-chat"),
    "reddit_longform": ("openrouter", "deepseek/deepseek-chat"),
    "x_thread":      ("openrouter", "deepseek/deepseek-chat"),
    "tiktok_script": ("openrouter", "deepseek/deepseek-chat"),
    "analysis":      ("anthropic", "claude-sonnet-4-5"),        # winner analysis = premium
}
DEFAULT_ROUTE = ("anthropic", "claude-sonnet-4-5")


def complete(system, user, task="copy_brief", max_tokens=900):
    provider, model = ROUTES.get(task, DEFAULT_ROUTE)
    if provider == "openrouter":
        return _openrouter(system, user, model, max_tokens)
    if provider == "anthropic":
        return _anthropic(system, user, model, max_tokens)
    if provider == "openai":
        return _openai(system, user, model, max_tokens)
    raise ValueError(f"unknown provider {provider}")


def _openrouter(system, user, model, max_tokens):
    from openai import OpenAI  # OpenRouter is OpenAI-API-compatible
    client = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=os.environ["OPENROUTER_API_KEY"])
    r = client.chat.completions.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}])
    return r.choices[0].message.content


def _anthropic(system, user, model, max_tokens):
    import anthropic
    client = anthropic.Anthropic()
    m = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                               messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in m.content if b.type == "text")


def _openai(system, user, model, max_tokens):
    from openai import OpenAI
    client = OpenAI()
    r = client.chat.completions.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}])
    return r.choices[0].message.content
