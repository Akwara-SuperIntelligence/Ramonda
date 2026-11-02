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
import os
from dataclasses import dataclass
from pathlib import Path

from temporalio import activity


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
    """A scripted model, so the loop is testable before it is smart.

    Sources: talk §04 (the model selects a tool call), lesson 01.
    Delta: increment 2 replaces this body with a real model client. The
    workflow and its tests do not change, because the model is already an
    activity rather than a line of workflow code.
    """
    if step == 0:
        return ModelReply(kind="tool", tool="echo", argument=history[-1])
    return ModelReply(kind="final", text=f"done in {len(history)} context entries")


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
