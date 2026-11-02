#!/usr/bin/env python3
"""Lesson 05: measure the prompt cache.

Three calls with a stable prefix, then three with a changing timestamp at the
front. Same content, different cache behaviour.

    .venv/bin/python build/lesson-05/meter.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
POLICY = "Policy: be concise, accurate, and explicit about uncertainty. " * 300


def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def client() -> tuple[OpenAI, str]:
    load_env()
    if os.environ.get("DEEPSEEK_API_KEY"):
        return OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com"), os.environ.get(
            "MODEL", "deepseek-chat"
        )
    if os.environ.get("OPENROUTER_API_KEY"):
        return OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1"), os.environ.get(
            "MODEL", "deepseek/deepseek-chat"
        )
    raise SystemExit("No model key in .env")


def call(api: OpenAI, model: str, label: str, system: str) -> None:
    response = api.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": "Reply with the single word OK."},
        ],
        max_tokens=5,
    )
    usage = response.usage
    hit = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
    miss = getattr(usage, "prompt_cache_miss_tokens", 0) or 0
    print(f"{label:10} prompt={usage.prompt_tokens:5}  hit={hit:5}  miss={miss:5}", flush=True)
    assert hit + miss == usage.prompt_tokens, "cache fields do not add up"


def main() -> None:
    api, model = client()
    print(f"model: {model}\nprefix chars: {len(POLICY)}\n")
    for i in range(1, 4):
        call(api, model, f"stable {i}", POLICY)
    for i in range(1, 4):
        call(api, model, f"unstable {i}", f"Request id: {time.time_ns()}\n" + POLICY)
    print("\nStable prefix: most tokens come from the cache after the first call.")
    print("One changed token at the front: no cache hit, every call pays in full.")


if __name__ == "__main__":
    main()
