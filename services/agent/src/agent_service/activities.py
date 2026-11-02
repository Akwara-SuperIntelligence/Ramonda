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

from dataclasses import dataclass

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
    """Execute one tool call.

    Sources: talk §04 (the harness, not the model, executes tools); EDA §5
    (every effect carries a token, so a retry is safe).

    Delta: the token is accepted but not yet enforced. Increment 3 adds the
    inbox table that makes a duplicate token a no-op.
    """
    if name == "echo":
        return ToolResult(ok=True, output=f"{argument} [token={effect_token}]")
    return ToolResult(ok=False, output=f"unknown tool: {name}")
