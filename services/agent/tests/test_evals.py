"""Evals: behaviour, graded from real failures.

Sources
    talk §06 — a failure becomes an eval; the inner loop
    lesson 10 — deterministic assertions over real model behaviour

Delta
    Two cases. The repeat rule (the send_email double call) and memory recall
    (the fact injected into the next turn). Each asserts on the live model with
    temperature 0, and skips when no key is present. A failure here blocks the
    behaviour, not the mechanics: the unit suite covers mechanics.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from agent_service import activities
from agent_service.activities import call_model, load_history, run_tool

pytestmark = [
    pytest.mark.filterwarnings("ignore::DeprecationWarning"),
    pytest.mark.skipif(
        not (
            os.environ.get("DEEPSEEK_API_KEY")
            or any(
                (folder / ".env").is_file()
                for folder in Path(__file__).resolve().parents
            )
        ),
        reason="no DEEPSEEK_API_KEY",
    ),
]


def _conv() -> str:
    return f"eval-{uuid4().hex}"


async def _seed_fact(conv: str, content: str) -> None:
    async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
        await conn.execute(
            "insert into memories (org_id, conversation_id, kind, content)"
            " values ('local', %s, 'fact', %s)",
            (conv, content),
        )


async def _seed_tool_step(conv: str, content: str) -> None:
    async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
        await conn.execute(
            "insert into messages (org_id, conversation_id, seq, step, role, content)"
            " values ('local', %s, 0, 1, 'tool', %s)",
            (conv, content),
        )


def test_the_repeat_rule_holds_after_a_succeeded_tool():
    """The model repeated send_email after success and claimed nothing was sent."""
    conv = _conv()
    asyncio.run(_seed_tool_step(conv, "echo(hello) -> hello"))
    loaded = asyncio.run(load_history("local", conv))
    history = loaded.messages + [
        {"role": "user", "content": "Say the echo already ran. Do not call it again."}
    ]

    reply = asyncio.run(
        call_model("local", conv, 0, 0, activities.PROMPT_VERSION, "", history)
    )

    assert reply.kind == "final", f"model repeated a succeeded tool: {reply}"


def test_a_fact_is_used_from_memory():
    """Memory must reach the answer, not only the prompt."""
    conv = _conv()
    asyncio.run(_seed_fact(conv, "The user's favourite colour is teal."))
    loaded = asyncio.run(load_history("local", conv))
    history = loaded.messages + [
        {"role": "user", "content": "What is my favourite colour? One word."}
    ]

    reply = asyncio.run(
        call_model("local", conv, 0, 0, activities.PROMPT_VERSION, "", history)
    )

    assert reply.kind == "final"
    assert "teal" in reply.text.lower(), f"fact did not reach the answer: {reply.text}"


def test_recall_finds_what_the_agent_wrote():
    """recall is the retrieval ladder's first rung for the agent's own work."""
    conv = _conv()
    asyncio.run(run_tool("local", conv, "remember", "the deploy window is Friday", f"tok-{uuid4().hex}"))

    result = asyncio.run(
        run_tool("local", conv, "recall", "deploy window", f"tok-{uuid4().hex}")
    )

    assert result.ok
    assert "Friday" in result.output