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
import hashlib
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agent_service import activities
from agent_service.activities import (
    acquire_lock,
    call_model,
    compact,
    expire_approval,
    load_history,
    next_turn,
    pin_prompt,
    release_lock,
    request_approval,
    run_tool,
    save_tool_step,
    send_user,
)
from agent_service.consumer import TASK_QUEUE as SERVICE_QUEUE
from agent_service.consumer import handle
from agent_service.events import APPROVAL_RESOLVED, SEND_MESSAGE, TYPING, Envelope
from agent_service.relay import relay_once
from agent_service.workflow import RunRequest, RunWorkflow

TASK_QUEUE = "test"

ACTIVITIES = [
    acquire_lock,
    call_model,
    compact,
    expire_approval,
    load_history,
    next_turn,
    pin_prompt,
    release_lock,
    request_approval,
    run_tool,
    save_tool_step,
    send_user,
]


def _fake_model(monkeypatch, *replies: str) -> list[dict]:
    """Answer each model call from a script, and keep what the model was sent."""
    script = iter(replies)
    seen: list[dict] = []

    def fake(payload: dict) -> dict:
        seen.append(payload)
        return {
            "choices": [{"message": {"content": next(script)}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "prompt_cache_hit_tokens": 6,
                "prompt_cache_miss_tokens": 4,
            },
        }

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


async def _column(query: str, params: tuple):
    async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
        cursor = await conn.execute(query, params)
        return [row[0] async for row in cursor]


def test_a_turn_is_saved_once(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"tool": "echo", "argument": "hello"}', '{"final": "done"}')

    result = asyncio.run(_run(RunRequest(conv, "hello"), f"run:{conv}:0"))

    assert result.reply == "done"
    assert asyncio.run(
        _column("select role from messages where conversation_id = %s order by seq, step", (conv,))
    ) == ["user", "tool", "assistant"]
    token = f"local:run:{conv}:0:0"
    assert asyncio.run(
        _scalar("select count(*) from effects where token = %s", (token,))
    ) == 1
    assert asyncio.run(
        _scalar("select count(*) from outbox where id = %s", (f"local:run:{conv}:0:save",))
    ) == 1
    assert asyncio.run(
        _scalar(
            "select cache_hit from model_calls where conversation_id = %s and seq = 0 and step = 0",
            (conv,),
        )
    ) == 6
    assert asyncio.run(
        _scalar(
            "select prompt_hash from model_calls where conversation_id = %s and seq = 0 and step = 0",
            (conv,),
        )
    ) == hashlib.sha256(activities.PROMPTS[activities.PROMPT_VERSION]["system"].encode()).hexdigest()[:12]


def test_a_duplicate_token_writes_once():
    token = f"dup-{uuid4().hex}"

    asyncio.run(run_tool("local", "dup", "echo", "first", token))
    asyncio.run(run_tool("local", "dup", "echo", "second", token))

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

    asyncio.run(_run(RunRequest(conv, "first"), f"run:{conv}:0"))
    asyncio.run(_run(RunRequest(conv, "second"), f"run:{conv}:1"))

    assert any("first" in m["content"] for m in seen[-1]["messages"])
    assert asyncio.run(
        _scalar("select count(*) from messages where conversation_id = %s", (conv,))
    ) == 5


def test_step_budget_is_enforced(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"tool": "echo", "argument": "hello"}')

    with pytest.raises(WorkflowFailureError):
        asyncio.run(_run(RunRequest(conv, "hello", max_steps=1), f"run:{conv}:0"))


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
    ) == 3


def test_relay_publishes_each_row_once():
    class Producer:
        def __init__(self):
            self.sent: list[tuple[str, bytes]] = []

        async def send_and_wait(self, topic: str, value: bytes) -> None:
            self.sent.append((topic, value))

    producer = Producer()
    asyncio.run(relay_once(producer))  # drain rows left by other tests
    token = f"relay-{uuid4().hex}"
    asyncio.run(send_user("acme", "relay", 0, 1, "u", "a", token))

    assert asyncio.run(relay_once(producer)) == 1
    assert producer.sent[-1][0] == "agent.messages"
    assert asyncio.run(relay_once(producer)) == 0


def _approval_id(conv: str) -> str:
    return f"local:run:{conv}:0:0:approval"


async def _start_and_resolve(conv: str, decision: str | None):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=SERVICE_QUEUE,
            workflows=[RunWorkflow],
            activities=ACTIVITIES,
        ):
            wf = await env.client.start_workflow(
                RunWorkflow.run,
                RunRequest(conv, "send mail"),
                id=f"run:{conv}:0",
                task_queue=SERVICE_QUEUE,
            )
            if decision is not None:
                for _ in range(200):
                    if await _scalar(
                        "select count(*) from approvals where id = %s",
                        (_approval_id(conv),),
                    ):
                        break
                    await asyncio.sleep(0.05)
                await handle(
                    env.client,
                    Envelope(
                        event_id=f"resolve:{conv}",
                        type=APPROVAL_RESOLVED,
                        org_id="local",
                        subject={"approval_id": _approval_id(conv)},
                        payload={"approval_id": _approval_id(conv), "decision": decision},
                    ),
                )
            return await wf.result()


def test_an_irreversible_tool_runs_only_after_approval(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"tool": "send_email", "argument": "a@b"}', '{"final": "sent"}')

    result = asyncio.run(_start_and_resolve(conv, "approved"))

    assert result.reply == "sent"
    assert asyncio.run(
        _scalar("select count(*) from effects where token = %s", (f"local:run:{conv}:0:0",))
    ) == 1
    assert asyncio.run(
        _scalar("select status from approvals where id = %s", (_approval_id(conv),))
    ) == "approved"


def test_a_denied_tool_does_not_run(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"tool": "send_email", "argument": "a@b"}', '{"final": "ok"}')

    asyncio.run(_start_and_resolve(conv, "denied"))

    assert asyncio.run(
        _scalar("select count(*) from effects where token = %s", (f"local:run:{conv}:0:0",))
    ) == 0


def test_an_unanswered_approval_expires(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"tool": "send_email", "argument": "a@b"}', '{"final": "ok"}')

    asyncio.run(_start_and_resolve(conv, None))

    assert asyncio.run(
        _scalar("select status from approvals where id = %s", (_approval_id(conv),))
    ) == "expired"
    assert asyncio.run(
        _scalar("select count(*) from effects where token = %s", (f"local:run:{conv}:0:0",))
    ) == 0


def test_the_conversation_lock_is_exclusive():
    conv = f"lock-{uuid4().hex}"

    async def scenario():
        first = await acquire_lock("local", conv, "wf-a")
        second = await acquire_lock("local", conv, "wf-b")
        await release_lock("local", conv, "wf-a")
        third = await acquire_lock("local", conv, "wf-b")
        await release_lock("local", conv, "wf-b")
        return first, second, third

    assert asyncio.run(scenario()) == (True, False, True)



def test_long_output_is_stored_and_readable():
    token = f"long-{uuid4().hex}"
    text = "x" * 3000

    result = asyncio.run(run_tool("local", "long", "echo", text, token))
    assert "[stored:" in result.output

    name = hashlib.sha256(token.encode()).hexdigest()[:16] + ".txt"
    assert asyncio.run(run_tool("local", "long", "read_file", name, token)).output == text


def test_compaction_summarises_old_turns(monkeypatch):
    conv = f"t-{uuid4().hex}"
    monkeypatch.setattr(activities, "COMPACT_AFTER", 2)
    monkeypatch.setattr(activities, "_summarize", lambda text: "summary of old turns")

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            for seq in range(10):
                await conn.execute(
                    "insert into messages (org_id, conversation_id, seq, step, role, content)"
                    " values ('local', %s, %s, 0, 'user', 'u'),"
                    " ('local', %s, %s, 1, 'assistant', 'a')",
                    (conv, seq, conv, seq),
                )

    asyncio.run(seed())
    asyncio.run(activities.compact("local", conv))

    assert asyncio.run(
        _scalar("select summary from conversations where conversation_id = %s", (conv,))
    ) == "summary of old turns"
    assert asyncio.run(
        _scalar("select summary_seq from conversations where conversation_id = %s", (conv,))
    ) == 3


def test_tool_schemas_are_loaded_on_demand():
    assert "send_email:" not in activities.SYSTEM
    assert "get_tool_schema:" in activities.SYSTEM

    token = f"schema-{uuid4().hex}"
    schema = asyncio.run(run_tool("local", "schema", "get_tool_schema", "send_email", token))
    assert schema.ok
    assert '"tool": "send_email"' in schema.output

    assert not asyncio.run(run_tool("local", "schema", "get_tool_schema", "nope", token)).ok


def _has_api_key() -> bool:
    if os.environ.get("DEEPSEEK_API_KEY"):
        return True
    return any((folder / ".env").is_file() for folder in Path(__file__).resolve().parents)


@pytest.mark.skipif(not _has_api_key(), reason="no DEEPSEEK_API_KEY")
def test_compaction_uses_the_live_model():
    conv = f"t-{uuid4().hex}"

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            for seq in range(12):
                await conn.execute(
                    "insert into messages (org_id, conversation_id, seq, step, role, content)"
                    " values ('local', %s, %s, 0, 'user', %s),"
                    " ('local', %s, %s, 1, 'assistant', %s)",
                    (conv, seq, f"question {seq} about invoices",
                     conv, seq, f"answer {seq} with a decision"),
                )

    asyncio.run(seed())
    asyncio.run(activities.compact("local", conv))

    summary = asyncio.run(
        _scalar("select summary from conversations where conversation_id = %s", (conv,))
    )
    assert summary
    assert len(summary) > 10
    assert asyncio.run(
        _scalar("select summary_seq from conversations where conversation_id = %s", (conv,))
    ) == 5


def test_prompt_version_is_pinned(monkeypatch):
    conv = f"t-{uuid4().hex}"
    first = asyncio.run(activities.pin_prompt("local", conv))
    monkeypatch.setattr(activities, "PROMPT_VERSION", "3")
    second = asyncio.run(activities.pin_prompt("local", conv))

    assert (first, second) == ("2", "2")


def test_an_unknown_prompt_version_fails_loudly():
    with pytest.raises(activities.ApplicationError):
        asyncio.run(activities.call_model("local", "c", 0, 0, "nope", "", []))


def test_typing_prewarms_without_a_turn(monkeypatch):
    conv = f"t-{uuid4().hex}"
    seen = _fake_model(monkeypatch, '{"final": "ok"}')
    envelope = Envelope(
        event_id=f"typing-{uuid4().hex}",
        type=TYPING,
        org_id="acme",
        subject={"conversation_id": conv},
        payload={},
    )

    assert asyncio.run(handle(None, envelope)) is None
    assert seen and seen[0]["messages"][0]["role"] == "system"
    assert asyncio.run(
        _scalar("select count(*) from messages where conversation_id = %s", (conv,))
    ) == 0


def test_every_activity_is_registered():
    from agent_service import worker

    defined = {
        value.__temporal_activity_definition.name
        for value in vars(activities).values()
        if hasattr(value, "__temporal_activity_definition")
    }
    registered = {
        value.__temporal_activity_definition.name for value in worker.ACTIVITIES
    }

    assert defined == registered


def test_a_fact_survives_into_the_next_turn(monkeypatch):
    conv = f"t-{uuid4().hex}"
    seen = _fake_model(
        monkeypatch,
        '{"tool": "remember", "argument": "My name is Hassan"}',
        '{"final": "noted"}',
        '{"final": "ok"}',
    )

    asyncio.run(_run(RunRequest(conv, "remember my name"), f"turn:{uuid4().hex}"))
    asyncio.run(_run(RunRequest(conv, "what is my name"), f"turn:{uuid4().hex}"))

    assert any("My name is Hassan" in m["content"] for m in seen[-1]["messages"])


def test_scratch_expires_but_facts_stay():
    conv = f"t-{uuid4().hex}"

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "insert into memories (org_id, conversation_id, kind, content, created_at)"
                " values ('local', %s, 'fact', 'durable fact', now()),"
                " ('local', %s, 'scratch', 'fresh note', now()),"
                " ('local', %s, 'scratch', 'stale note', now() - interval '2 hours')",
                (conv, conv, conv),
            )

    asyncio.run(seed())
    loaded = asyncio.run(activities.load_history("local", conv))
    text = "\n".join(message["content"] for message in loaded.messages)

    assert "durable fact" in text
    assert "fresh note" in text
    assert "stale note" not in text


def test_recall_finds_an_old_message():
    conv = f"t-{uuid4().hex}"

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "insert into messages (org_id, conversation_id, seq, step, role, content)"
                " values ('local', %s, 0, 0, 'user', 'invoice 42 was paid')",
                (conv,),
            )

    asyncio.run(seed())
    result = asyncio.run(
        run_tool("local", conv, "recall", "invoice", f"recall-{uuid4().hex}")
    )

    assert result.ok
    assert "invoice 42 was paid" in result.output


def test_read_skill_stays_in_the_skills_directory():
    good = asyncio.run(
        run_tool("local", "c", "read_skill", "status-update", f"skill-{uuid4().hex}")
    )
    bad = asyncio.run(
        run_tool("local", "c", "read_skill", "../../etc/passwd", f"skill-{uuid4().hex}")
    )

    assert good.ok and "status update" in good.output.lower()
    assert not bad.ok
