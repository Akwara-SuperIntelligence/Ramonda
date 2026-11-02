"""Behaviour of a conversation.

Sources
    lesson 01 — a turn is three steps, repeated
    lesson 02 — a failure must not cost the turn its state
    lesson 07 — the conversation is remembered across turns
    EDA §5 — every effect carries a token

Delta
    The time-skipping test environment replaces a running Temporal server, and
    Postgres is real, so the store is exercised as the worker exercises it.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import psycopg
import pytest
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agent_service import activities
from agent_service.activities import call_model, load_history, run_tool, save_turn
from agent_service.consumer import TASK_QUEUE as SERVICE_QUEUE
from agent_service.consumer import handle
from agent_service.events import SEND_MESSAGE, Envelope
from agent_service.workflow import RunRequest, RunWorkflow

TASK_QUEUE = "test"

ACTIVITIES = [call_model, load_history, run_tool, save_turn]


def _fake_model(monkeypatch, *replies: str) -> list[dict]:
    """Answer each model call from a script, and keep what the model was sent."""
    script = iter(replies)
    seen: list[dict] = []

    def fake(payload: dict) -> dict:
        seen.append(payload)
        return {"choices": [{"message": {"content": next(script)}}]}

    monkeypatch.setattr(activities, "_post", fake)
    return seen


async def _run(request: RunRequest, workflow_id: str):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[RunWorkflow],
            activities=ACTIVITIES,
        ):
            return await env.client.execute_workflow(
                RunWorkflow.run,
                request,
                id=workflow_id,
                task_queue=TASK_QUEUE,
            )


async def _scalar(query: str, params: tuple):
    async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
        cursor = await conn.execute(query, params)
        row = await cursor.fetchone()
        return row[0] if row else None


def test_a_turn_is_saved_once(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"tool": "echo", "argument": "hello"}', '{"final": "done"}')

    result = asyncio.run(_run(RunRequest(conv, "hello", seq=0), f"run:{conv}:0"))

    assert result.reply == "done"
    assert asyncio.run(
        _scalar("select count(*) from messages where conversation_id = %s", (conv,))
    ) == 2
    token = f"local:run:{conv}:0:0"
    assert asyncio.run(
        _scalar("select count(*) from effects where token = %s", (token,))
    ) == 1


def test_a_duplicate_token_writes_once():
    token = f"dup-{uuid4().hex}"

    asyncio.run(run_tool("echo", "first", token))
    asyncio.run(run_tool("echo", "second", token))

    assert asyncio.run(
        _scalar("select count(*) from effects where token = %s", (token,))
    ) == 1
    assert asyncio.run(
        _scalar("select payload from effects where token = %s", (token,))
    ) == "first"


def test_a_second_turn_sees_the_first(monkeypatch):
    conv = f"t-{uuid4().hex}"
    seen = _fake_model(
        monkeypatch,
        '{"tool": "echo", "argument": "hello"}',
        '{"final": "done"}',
        '{"final": "again"}',
    )

    asyncio.run(_run(RunRequest(conv, "first", seq=0), f"run:{conv}:0"))
    asyncio.run(_run(RunRequest(conv, "second", seq=1), f"run:{conv}:1"))

    assert "user: first" in seen[-1]["messages"][1]["content"]
    assert asyncio.run(
        _scalar("select count(*) from messages where conversation_id = %s", (conv,))
    ) == 4


def test_step_budget_is_enforced(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"tool": "echo", "argument": "hello"}')

    with pytest.raises(WorkflowFailureError):
        asyncio.run(_run(RunRequest(conv, "hello", seq=0, max_steps=1), f"run:{conv}:0"))


def test_an_event_starts_one_turn(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"tool": "echo", "argument": "hi"}', '{"final": "done"}')
    envelope = Envelope(
        event_id=f"e-{uuid4().hex}",
        type=SEND_MESSAGE,
        org_id="acme",
        subject={"conversation_id": conv},
        payload={"text": "hello"},
    )

    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue=SERVICE_QUEUE,
                workflows=[RunWorkflow],
                activities=ACTIVITIES,
            ):
                first = await handle(env.client, envelope)
                second = await handle(env.client, envelope)
                await first.result()
                return second

    assert asyncio.run(scenario()) is None
    assert asyncio.run(
        _scalar("select count(*) from inbox where event_id = %s", (envelope.event_id,))
    ) == 1
    assert asyncio.run(
        _scalar(
            "select count(*) from messages where conversation_id = %s and org_id = 'acme'",
            (conv,),
        )
    ) == 2
