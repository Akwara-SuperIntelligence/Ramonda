"""Activities: every effect a turn performs.

Sources
    talk §03 — the agent loop is a model calling tools, run on a server
    talk §04 — the harness executes the tool call; the model only names it
    lesson 01 — a turn is three steps, repeated
    lesson 02 — write the intent down before the effect

Delta
    Temporal executes these, and replays their results instead of running them
    again. The workflow asks for an effect; it never performs one.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from temporalio import activity

SYSTEM = """You are an agent on a server. You have one tool: echo.
Reply with one JSON object and nothing else.
Call the tool: {"tool": "echo", "argument": "<text>"}
Answer: {"final": "<text>"}
"""


@dataclass
class ModelReply:
    """What the model wants next."""

    kind: str  # "tool" or "final"
    text: str = ""
    tool: str = ""
    argument: str = ""


@dataclass
class ToolResult:
    """What the tool did."""

    ok: bool
    output: str


def _load_env() -> None:
    for folder in Path(__file__).resolve().parents:
        env = folder / ".env"
        if env.is_file():
            for line in env.read_text().splitlines():
                key, _, value = line.partition("=")
                if key and not key.startswith("#"):
                    os.environ.setdefault(key.strip(), value.strip())
            return


def _api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        _load_env()
        key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set; put it in .env at the repo root")
    return key


def _post(payload: dict) -> dict:
    request = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key()}",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def _parse_reply(text: str) -> ModelReply:
    raw = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ModelReply(kind="final", text=text)
    if "tool" in data:
        return ModelReply(kind="tool", tool=data["tool"], argument=str(data.get("argument", "")))
    return ModelReply(kind="final", text=str(data.get("final", raw)))


def _effects_dir() -> Path:
    return Path(os.environ.get("AGENT_EFFECTS_DIR", ".agent/effects"))


def _claim(token: str, payload: str) -> bool:
    """Record the effect once. True the first time; False on any repeat.

    The marker is linked into place only after its content is complete, so a
    crash leaves either no marker or a whole one.
    """
    folder = _effects_dir()
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / hashlib.sha256(token.encode()).hexdigest()
    temp = folder / f".{marker.name}.{os.getpid()}.tmp"
    temp.write_text(payload)
    try:
        os.link(temp, marker)
        return True
    except FileExistsError:
        return False
    finally:
        temp.unlink()


@activity.defn
async def call_model(step: int, history: list[str]) -> ModelReply:
    """Ask the real model what to do next.

    Sources: talk §04 (the model selects a tool call), talk §05 (a stable
    system prompt keeps the prefix cacheable), lesson 01.

    Delta: the scripted model is gone. The workflow and its interface did not
    change, because the model was already an activity.
    """
    body = _post(
        {
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": "\n".join(history)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
    )
    return _parse_reply(body["choices"][0]["message"]["content"])


@activity.defn
async def run_tool(name: str, argument: str, effect_token: str) -> ToolResult:
    """Execute one tool call, at most once per token.

    Sources: talk §04 (the harness, not the model, executes tools); EDA §5
    (every effect carries a token, so a retry is safe).

    Delta: the token is now enforced. A retried activity returns the same
    answer without repeating the effect.
    """
    if name == "echo":
        # shortcut: one host only, replaced by the Postgres inbox with the consumer.
        _claim(effect_token, argument)
        return ToolResult(ok=True, output=argument)
    return ToolResult(ok=False, output=f"unknown tool: {name}")
