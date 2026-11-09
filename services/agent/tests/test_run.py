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
import io
import json
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
import re
import os
import urllib.request
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agent_service import activities
from agent_service import consumer as consumer_module
from agent_service import maintenance
from agent_service import routines
from agent_service import storage
from agent_service import transcript
from agent_service.activities import (
    acquire_lock,
    call_model,
    compact,
    compact_steps,
    create_task,
    expire_approval,
    finish_task,
    list_tasks,
    load_history,
    next_turn,
    pin_prompt,
    plan_open,
    record_progress,
    record_run,
    release_lock,
    renew_lock,
    report_task,
    request_approval,
    reset_turn_state,
    review_action,
    routine_active,
    run_tool,
    save_tool_step,
    send_user,
    should_speak,
)
from agent_service.consumer import TASK_QUEUE as SERVICE_QUEUE
from agent_service.consumer import handle
from agent_service.events import RESOLVE_APPROVAL, SEND_MESSAGE, TYPING, Envelope
from agent_service.health import start_health_server
from agent_service.relay import relay_once
from agent_service.workflow import HELPER_QUEUE, HelperTask, HelperWorkflow, RunRequest, RunWorkflow

TASK_QUEUE = "test"

ACTIVITIES = [
    acquire_lock,
    call_model,
    compact,
    compact_steps,
    create_task,
    expire_approval,
    finish_task,
    list_tasks,
    load_history,
    next_turn,
    pin_prompt,
    plan_open,
    record_progress,
    record_run,
    release_lock,
    renew_lock,
    report_task,
    request_approval,
    reset_turn_state,
    review_action,
    routine_active,
    run_tool,
    save_tool_step,
    send_user,
    should_speak,
]


def _usage() -> dict:
    return {
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "prompt_cache_hit_tokens": 6,
            "prompt_cache_miss_tokens": 4,
        }
    }


def _fake_router(monkeypatch, routes: list[tuple], seen: list | None = None) -> list:
    """First matching substring wins. A callable reply gets (last, payload)."""
    seen = [] if seen is None else seen

    def fake(payload: dict) -> dict:
        seen.append(payload)
        last = payload["messages"][-1]["content"]
        for matcher, reply in routes:
            hit = matcher(last, payload) if callable(matcher) else last == matcher
            if hit:
                content = reply(last, payload) if callable(reply) else reply
                return {
                    "choices": [{"message": {"content": content}}],
                    **_usage(),
                }
        raise AssertionError(f"no route for: {last!r}")

    monkeypatch.setattr(activities, "_post", fake)
    return seen


def _fake_model(
    monkeypatch,
    *replies: str,
    review: str = '{"verdict": "allow", "reason": "safe"}',
) -> list[dict]:
    """Answer each model call from a script, and keep what the model was sent.

    A reviewer call gets `review`; the script feeds the main loop only.
    """
    script = iter(replies)
    seen: list[dict] = []

    def fake(payload: dict) -> dict:
        seen.append(payload)
        system = payload["messages"][0]["content"]
        content = review if "security reviewer" in system else next(script)
        return {
            "choices": [{"message": {"content": content}}],
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
    assert [entry["role"] for entry in transcript.load("local", conv)] == [
        "user",
        "tool",
        "assistant",
    ]
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
    assert len(transcript.load("local", conv)) == 5


def test_step_budget_is_enforced(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"tool": "echo", "argument": "hello"}')

    result = asyncio.run(_run(RunRequest(conv, "hello", max_steps=1), f"run:{conv}:0"))
    assert result.budget_exhausted is True
    assert "step budget" in result.reply


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
    assert len(transcript.load("acme", conv)) == 3


def test_a_failed_inbox_write_does_not_lose_the_turn(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"final": "done"}')
    envelope = Envelope(
        event_id=f"e-{uuid4().hex}",
        type=SEND_MESSAGE,
        org_id="acme",
        subject={"conversation_id": conv},
        payload={"text": "hello"},
    )
    claim = consumer_module._claim
    attempts: list[str] = []

    async def flaky(env):
        attempts.append(env.event_id)
        if len(attempts) == 1:
            raise RuntimeError("database down")
        return await claim(env)

    monkeypatch.setattr(consumer_module, "_claim", flaky)

    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue=SERVICE_QUEUE,
                workflows=[RunWorkflow],
                activities=ACTIVITIES,
            ):
                with pytest.raises(RuntimeError):
                    await handle(env.client, envelope)
                second = await handle(env.client, envelope)
                await second.result()
                return second

    assert asyncio.run(scenario()) is not None
    assert len(attempts) == 2
    assert asyncio.run(
        _scalar("select count(*) from inbox where event_id = %s", (envelope.event_id,))
    ) == 1
    assert len(transcript.load("acme", conv)) == 2


def test_a_second_approval_decision_is_ignored():
    approval_id = f"approval-{uuid4().hex}"

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "insert into approvals"
                " (id, org_id, conversation_id, workflow_id, action, arguments)"
                " values (%s, 'local', 'c', 'wf', 'send_email', 'a@b')",
                (approval_id,),
            )

    class Handle:
        def __init__(self) -> None:
            self.decisions: list[str] = []
            self.arguments: list[str | None] = []

        async def signal(self, name: str, args: list) -> None:
            self.decisions.append(args[0])
            self.arguments.append(args[2])

    class Client:
        def __init__(self) -> None:
            self.handle = Handle()

        def get_workflow_handle(self, workflow_id: str) -> Handle:
            return self.handle

    def envelope(
        decision: str, event_id: str, argument: str | None = None
    ) -> Envelope:
        payload = {"approval_id": approval_id, "decision": decision}
        if argument is not None:
            payload["argument"] = argument
        return Envelope(
            event_id=event_id,
            type=RESOLVE_APPROVAL,
            org_id="local",
            subject={"approval_id": approval_id},
            payload=payload,
        )

    asyncio.run(seed())
    client = Client()
    first_id = f"resolve-{uuid4().hex}"
    first = asyncio.run(handle(client, envelope("approved", first_id)))
    second = asyncio.run(handle(client, envelope("denied", f"resolve-{uuid4().hex}")))
    third = asyncio.run(
        handle(client, envelope("approved", f"resolve-{uuid4().hex}", "hacked"))
    )

    assert first is not None and second is None and third is not None
    assert client.handle.decisions == ["approved", "approved"]
    assert client.handle.arguments == ["a@b", "a@b"]
    assert asyncio.run(
        _scalar("select arguments from approvals where id = %s", (approval_id,))
    ) == "a@b"
    assert asyncio.run(
        _scalar("select status from approvals where id = %s", (approval_id,))
    ) == "approved"
    assert asyncio.run(
        _scalar("select count(*) from inbox where event_id = %s", (first_id,))
    ) == 1


def test_relay_publishes_each_row_once():
    class Producer:
        def __init__(self):
            self.sent: list[tuple[str, bytes]] = []

        async def send_and_wait(self, topic: str, value: bytes) -> None:
            self.sent.append((topic, value))

    producer = Producer()
    while asyncio.run(relay_once(producer)):
        pass
    token = f"relay-{uuid4().hex}"
    asyncio.run(send_user("acme", "relay", 0, 1, "u", "a", token))

    assert asyncio.run(relay_once(producer)) >= 1
    published = [Envelope.from_json(value) for _, value in producer.sent]
    assert any(envelope.event_id == token for envelope in published)
    before = len(producer.sent)
    asyncio.run(relay_once(producer))
    again = [Envelope.from_json(value) for _, value in producer.sent[before:]]
    assert not any(envelope.event_id == token for envelope in again)


def _approval_id(conv: str) -> str:
    return f"local:run:{conv}:0:0:approval"


async def _start_and_resolve(conv: str, decision: str | None, **extra):
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
                        type=RESOLVE_APPROVAL,
                        org_id="local",
                        subject={"approval_id": _approval_id(conv)},
                        payload={
                            "approval_id": _approval_id(conv),
                            "decision": decision,
                            **extra,
                        },
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
    payload = json.loads(
        asyncio.run(
            _scalar("select payload::text from approvals where id = %s", (_approval_id(conv),))
        )
    )
    assert payload["kind"] == "action"
    assert [field["label"] for field in payload["fields"]] == ["To", "Message"]
    assert payload["review"]["verdict"] == "allow"


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
    assert asyncio.run(
        _scalar(
            "select count(*) from outbox where id = %s",
            (f"approval-resolved:{_approval_id(conv)}:expired",),
        )
    ) == 1


def test_a_reviewer_denial_does_not_ask_the_human(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(
        monkeypatch,
        '{"tool": "send_email", "argument": "a@b"}',
        '{"final": "ok"}',
        review='{"verdict": "deny", "reason": "looks unsafe"}',
    )

    result = asyncio.run(_run(RunRequest(conv, "send mail"), f"turn:{uuid4().hex}"))

    assert result.reply == "ok"
    assert asyncio.run(
        _scalar("select verdict from reviews where conversation_id = %s", (conv,))
    ) == "deny"
    assert asyncio.run(
        _scalar("select count(*) from approvals where conversation_id = %s", (conv,))
    ) == 0


def test_reviewer_failure_escalates_to_the_human(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"tool": "send_email", "argument": "a@b"}', '{"final": "sent"}', review="not json")

    result = asyncio.run(_start_and_resolve(conv, "approved"))

    assert result.reply == "sent"
    payload = json.loads(
        asyncio.run(
            _scalar("select payload::text from approvals where id = %s", (_approval_id(conv),))
        )
    )
    assert payload["review"]["verdict"] == "escalate"


def test_editing_an_approval_changes_the_effect(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"tool": "send_email", "argument": "a@b original"}', '{"final": "sent"}')

    result = asyncio.run(
        _start_and_resolve(conv, "approved", argument="c@d edited")
    )

    assert result.reply == "sent"
    assert asyncio.run(
        _scalar("select payload from effects where token = %s", (f"local:run:{conv}:0:0",))
    ) == "c@d edited"
    assert asyncio.run(
        _scalar("select arguments from approvals where id = %s", (_approval_id(conv),))
    ) == "c@d edited"
    resolved = json.loads(
        asyncio.run(
            _scalar(
                "select payload from outbox where id = %s",
                (f"approval-resolved:{_approval_id(conv)}:approved",),
            )
        )
    )["payload"]
    assert resolved["decision"] == "approved"
    assert resolved["argument"] == "c@d edited"


def test_editing_fields_changes_the_effect(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(monkeypatch, '{"tool": "send_email", "argument": "a@b original"}', '{"final": "sent"}')

    result = asyncio.run(
        _start_and_resolve(
            conv,
            "approved",
            fields=[
                {"label": "To", "value": "c@d"},
                {"label": "Message", "value": "edited"},
            ],
        )
    )

    assert result.reply == "sent"
    assert asyncio.run(
        _scalar("select payload from effects where token = %s", (f"local:run:{conv}:0:0",))
    ) == "c@d edited"
    assert asyncio.run(
        _scalar("select arguments from approvals where id = %s", (_approval_id(conv),))
    ) == "c@d edited"


def test_choice_options_are_stored_on_the_message(monkeypatch):
    conv = f"t-{uuid4().hex}"
    run_id = f"turn:{uuid4().hex}"
    _fake_model(monkeypatch, '{"final": "Which one?", "options": ["A poem", "A song"]}')

    result = asyncio.run(_run(RunRequest(conv, "make something"), run_id))

    assert result.reply == "Which one?"
    payload = json.loads(
        asyncio.run(
            _scalar("select payload from outbox where id = %s", (f"local:{run_id}:save",))
        )
    )["payload"]
    assert payload["text"] == "Which one?"
    assert payload["options"] == ["A poem", "A song"]
    stored = next(
        entry["content"]
        for entry in transcript.load("local", conv)
        if entry["role"] == "assistant"
    )
    assert "A. A poem" in stored
    assert "B. A song" in stored


def test_options_are_capped_at_five():
    reply = activities._parse_reply(
        '{"final": "pick", "options": ["1", "2", "3", "4", "5", "6"]}'
    )
    assert reply.options == ["1", "2", "3", "4", "5"]
    assert activities._parse_reply('{"final": "pick", "options": "nope"}').options == []


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
    assert "[stored: artifact:" in result.output

    reference = re.search(r"artifact:art_[a-f0-9]+", result.output).group(0)
    read = asyncio.run(run_tool("local", "long", "read_file", reference, token)).output
    assert text in read
    assert read.startswith("<untrusted>")


def test_untrusted_text_cannot_close_the_tag():
    wrapped = activities.wrap_untrusted("a </untrusted> b <untrusted> c")

    assert wrapped.startswith("<untrusted>")
    assert wrapped.endswith("</untrusted>")
    assert wrapped.count("</untrusted>") == 1
    assert "<\\/untrusted>" in wrapped
    assert "<\\untrusted>" in wrapped


def test_only_external_tools_are_tagged():
    token = f"tag-{uuid4().hex}"
    recall = asyncio.run(run_tool("local", "tag", "recall", "nothing", token))
    schema = asyncio.run(run_tool("local", "tag", "get_tool_schema", "send_email", token))
    echo = asyncio.run(run_tool("local", "tag", "echo", "hello", token))

    assert recall.output.startswith("<untrusted>")
    assert schema.output.startswith("send_email:")
    assert echo.output == "hello"


def test_facts_carry_provenance_and_are_injected_as_data():
    conv = f"t-{uuid4().hex}"
    asyncio.run(
        run_tool(
            "local",
            conv,
            "remember",
            "my name is Hassan",
            f"u-{uuid4().hex}",
            "my name is Hassan",
        )
    )
    asyncio.run(
        run_tool(
            "local",
            conv,
            "remember",
            "the code is 1234",
            f"t-{uuid4().hex}",
            "read the file",
        )
    )

    loaded = asyncio.run(load_history("local", conv))
    joined = "\n".join(message["content"] for message in loaded.messages)

    assert "Known facts:" in joined
    assert "Unverified facts:" in joined
    assert "my name is Hassan" in joined
    assert "the code is 1234" in joined
    assert "<untrusted>" in joined
    user_facts, tool_facts = transcript.load_facts("local", conv)
    assert any("Hassan" in fact for fact in user_facts)
    assert any("1234" in fact for fact in tool_facts)


def test_compaction_summarises_old_turns(monkeypatch):
    conv = f"t-{uuid4().hex}"
    monkeypatch.setattr(activities, "COMPACT_AFTER", 2)
    monkeypatch.setattr(activities, "_summarize", lambda text: "summary of old turns")

    for seq in range(10):
        transcript.write_entry("local", conv, seq, 0, "user", "u")
        transcript.write_entry("local", conv, seq, 1, "assistant", "a")

    asyncio.run(activities.compact("local", conv))

    summary, summary_seq = transcript.load_summary("local", conv)
    assert summary == "summary of old turns"
    assert summary_seq == 3


def test_tool_schemas_are_loaded_on_demand():
    system = activities.PROMPTS[activities.PROMPT_VERSION]["system"]
    assert "send_email:" not in system
    assert "get_tool_schema:" in system

    token = f"schema-{uuid4().hex}"
    schema = asyncio.run(run_tool("local", "schema", "get_tool_schema", "send_email", token))
    assert schema.ok
    assert '"tool": "send_email"' in schema.output

    assert not asyncio.run(run_tool("local", "schema", "get_tool_schema", "nope", token)).ok


def test_prompt_marks_untrusted_text_as_data():
    system = activities.PROMPTS[activities.PROMPT_VERSION]["system"]

    assert "<untrusted>" in system
    assert "external data" in system


def _has_api_key() -> bool:
    if os.environ.get("OPENROUTER_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"):
        return True
    return any((folder / ".env").is_file() for folder in Path(__file__).resolve().parents)


@pytest.mark.skipif(not _has_api_key(), reason="no model API key")
def test_compaction_uses_the_live_model():
    conv = f"t-{uuid4().hex}"

    for seq in range(12):
        transcript.write_entry("local", conv, seq, 0, "user", f"question {seq} about invoices")
        transcript.write_entry("local", conv, seq, 1, "assistant", f"answer {seq} with a decision")

    asyncio.run(activities.compact("local", conv))

    summary, summary_seq = transcript.load_summary("local", conv)
    assert summary
    assert len(summary) > 10
    assert summary_seq == 5


def test_prompt_version_is_pinned(monkeypatch):
    conv = f"t-{uuid4().hex}"
    first = asyncio.run(activities.pin_prompt("local", conv))
    monkeypatch.setattr(activities, "PROMPT_VERSION", "10")
    second = asyncio.run(activities.pin_prompt("local", conv))

    assert (first, second) == ("9", "9")


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
    assert transcript.load("acme", conv) == []


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
    transcript.add_fact("local", conv, "durable fact", "user")
    transcript.add_note("local", conv, "fresh note", "fresh-token")
    transcript.add_note("local", conv, "stale note", "stale-token")
    stale_path = storage.LOCAL_ROOT / transcript._scratch_key(
        "local", conv, "stale-token"
    )
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
    os.utime(stale_path, (old, old))

    loaded = asyncio.run(activities.load_history("local", conv))
    text = "\n".join(message["content"] for message in loaded.messages)

    assert "durable fact" in text
    assert "fresh note" in text
    assert "stale note" not in text


def test_recall_finds_an_old_message():
    conv = f"t-{uuid4().hex}"
    transcript.write_entry("local", conv, 0, 0, "user", "invoice 42 was paid")

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


def test_skills_match_their_folder_and_have_a_body():
    for folder in activities.SKILLS.iterdir():
        if not folder.is_dir():
            continue
        text = (folder / "SKILL.md").read_text()
        name = re.search(r"^name:\s*(\S+)$", text, re.M).group(1)
        body = text.split("---", 2)[2].strip()

        assert name == folder.name
        assert body





def test_a_helper_cannot_run_an_irreversible_tool(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(
        monkeypatch,
        '{"tool": "delegate", "argument": "send the email"}',
        '{"tool": "send_email", "argument": "a@b"}',
        '{"final": "could not send"}',
        '{"final": "the helper could not send it"}',
    )

    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue=SERVICE_QUEUE,
                workflows=[RunWorkflow],
                activities=ACTIVITIES,
            ):
                async with Worker(
                    env.client,
                    task_queue=HELPER_QUEUE,
                    workflows=[HelperWorkflow],
                    activities=ACTIVITIES,
                ):
                    return await env.client.execute_workflow(
                        RunWorkflow.run,
                        RunRequest(conv, "send the email"),
                        id=f"turn:{uuid4().hex}",
                        task_queue=SERVICE_QUEUE,
                    )

    asyncio.run(scenario())

    assert asyncio.run(
        _scalar(
            "select count(*) from effects where token like %s and kind = 'send_email'",
            ("helper:%",),
        )
    ) == 0
    assert asyncio.run(
        _scalar("select count(*) from approvals where conversation_id = %s", (conv,))
    ) == 0


def _two_workers(env_client):
    return [
        Worker(
            env_client,
            task_queue=SERVICE_QUEUE,
            workflows=[RunWorkflow],
            activities=ACTIVITIES,
        ),
        Worker(
            env_client,
            task_queue=HELPER_QUEUE,
            workflows=[HelperWorkflow],
            activities=ACTIVITIES,
        ),
    ]


async def _run_with_helpers(request: RunRequest):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with AsyncExitStack() as stack:
            for worker in _two_workers(env.client):
                await stack.enter_async_context(worker)
            return await env.client.execute_workflow(
                RunWorkflow.run,
                request,
                id=f"turn:{uuid4().hex}",
                task_queue=SERVICE_QUEUE,
            )


def _starts(prefix: str):
    return lambda last, payload: last.startswith(prefix)


def test_a_delegate_starts_and_collect_returns_the_report(monkeypatch):
    conv = f"t-{uuid4().hex}"
    started = {"n": 0}

    def on_started(last, payload):
        started["n"] += 1
        if started["n"] == 1:
            return '{"tool": "delegate", "argument": "do the B work"}'
        return '{"tool": "collect", "argument": "all"}'

    _fake_router(
        monkeypatch,
        [
            ("do the A work", '{"final": "A report"}'),
            ("do the B work", '{"final": "B report"}'),
            (_starts("tool result: delegate -> started"), on_started),
            ("coordinate the work", '{"tool": "delegate", "argument": "do the A work"}'),
            (_starts("tool result: collect"), '{"final": "both reports are in"}'),
        ],
    )

    result = asyncio.run(_run_with_helpers(RunRequest(conv, "coordinate the work")))

    assert result.reply == "both reports are in"
    entries = transcript.load("local", conv)
    assert [entry["role"] for entry in entries] == [
        "user",
        "tool",
        "tool",
        "tool",
        "assistant",
    ]
    assert any("A report" in entry["content"] for entry in entries)
    assert asyncio.run(
        _scalar("select count(*) from model_calls where conversation_id = %s and seq < 0", (conv,))
    ) == 2


def test_a_helper_cannot_run_an_irreversible_tool(monkeypatch):
    conv = f"t-{uuid4().hex}"

    _fake_router(
        monkeypatch,
        [
            (
                "tool result: send_email denied (helpers cannot run irreversible tools)",
                '{"final": "could not send it"}',
            ),
            ("send the email via helper", '{"tool": "send_email", "argument": "a@b"}'),
            ("coordinate the work", '{"tool": "delegate", "argument": "send the email via helper"}'),
            (_starts("tool result: delegate -> started"), '{"tool": "collect", "argument": "all"}'),
            (_starts("tool result: collect"), '{"final": "the helper could not send it"}'),
        ],
    )

    asyncio.run(_run_with_helpers(RunRequest(conv, "coordinate the work")))

    assert asyncio.run(
        _scalar(
            "select count(*) from effects where kind = 'send_email' and token like %s",
            ("helper:%",),
        )
    ) == 0
    assert asyncio.run(
        _scalar("select count(*) from approvals where conversation_id = %s", (conv,))
    ) == 0


def test_a_message_reaches_the_helper(monkeypatch):
    conv = f"t-{uuid4().hex}"
    seen: list = []

    def after_echo(last, payload):
        if any("the main agent says:" in m["content"] for m in payload["messages"]):
            return '{"final": "checked the red one"}'
        return '{"tool": "echo", "argument": "working"}'

    def on_started(last, payload):
        task_id = last.split("started ")[1]
        return '{"tool": "message_helper", "argument": "' + task_id + ' check the red one"}'

    _fake_router(
        monkeypatch,
        [
            (
                "the main agent says: check the red one",
                '{"final": "checked the red one"}',
            ),
            ("tool result: echo -> working", after_echo),
            ("do the A work", '{"tool": "echo", "argument": "working"}'),
            ("coordinate the work", '{"tool": "delegate", "argument": "do the A work"}'),
            (_starts("tool result: delegate -> started"), on_started),
            (_starts("tool result: message_helper"), '{"tool": "collect", "argument": "all"}'),
            (_starts("tool result: collect"), '{"final": "the helper checked it"}'),
        ],
        seen,
    )

    result = asyncio.run(_run_with_helpers(RunRequest(conv, "coordinate the work")))

    assert result.reply == "the helper checked it"
    assert any(
        "the main agent says: check the red one" in m["content"]
        for payload in seen
        for m in payload["messages"]
    )


def test_a_stopped_helper_reports_stopped(monkeypatch):
    conv = f"t-{uuid4().hex}"

    def on_started(last, payload):
        task_id = last.split("started ")[1]
        return '{"tool": "stop_helper", "argument": "' + task_id + '"}'

    _fake_router(
        monkeypatch,
        [
            ("do the A work", '{"tool": "echo", "argument": "working"}'),
            ("tool result: echo -> working", '{"tool": "echo", "argument": "working"}'),
            ("coordinate the work", '{"tool": "delegate", "argument": "do the A work"}'),
            (_starts("tool result: delegate -> started"), on_started),
            (_starts("tool result: stop_helper"), '{"tool": "collect", "argument": "all"}'),
            (_starts("tool result: collect"), '{"final": "the helper was stopped"}'),
        ],
    )

    result = asyncio.run(_run_with_helpers(RunRequest(conv, "coordinate the work")))

    assert result.reply == "the helper was stopped"
    assert any(
        "stopped" in entry["content"] for entry in transcript.load("local", conv)
    )
    assert asyncio.run(
        _scalar("select status from tasks where conversation_id = %s", (conv,))
    ) == "stopped"


def test_helpers_reports_task_status(monkeypatch):
    conv = f"t-{uuid4().hex}"
    asked = {"n": 0}

    def on_started(last, payload):
        return '{"tool": "helpers", "argument": ""}'

    def on_helpers(last, payload):
        asked["n"] += 1
        if asked["n"] == 1:
            return '{"tool": "collect", "argument": "all"}'
        return '{"final": "checked and collected"}'

    _fake_router(
        monkeypatch,
        [
            ("do the A work", '{"final": "A report"}'),
            ("coordinate the work", '{"tool": "delegate", "argument": "do the A work"}'),
            (_starts("tool result: delegate -> started"), on_started),
            (_starts("tool result: helpers"), on_helpers),
            (_starts("tool result: collect"), '{"tool": "helpers", "argument": ""}'),
        ],
    )

    result = asyncio.run(_run_with_helpers(RunRequest(conv, "coordinate the work")))

    assert result.reply == "checked and collected"
    rows = [
        entry["content"]
        for entry in transcript.load("local", conv)
        if entry["role"] == "tool"
    ]
    assert any("t1 " in row and "do the A work" in row for row in rows)
    assert any("t1 done" in row for row in rows)


def test_stop_all_stops_every_task(monkeypatch):
    conv = f"t-{uuid4().hex}"
    started = {"n": 0}

    def on_started(last, payload):
        started["n"] += 1
        if started["n"] == 1:
            return '{"tool": "delegate", "argument": "do the B work"}'
        return '{"tool": "stop_helper", "argument": "all"}'

    _fake_router(
        monkeypatch,
        [
            ("do the A work", '{"tool": "echo", "argument": "working"}'),
            ("do the B work", '{"tool": "echo", "argument": "working"}'),
            ("tool result: echo -> working", '{"tool": "echo", "argument": "working"}'),
            ("coordinate the work", '{"tool": "delegate", "argument": "do the A work"}'),
            (_starts("tool result: delegate -> started"), on_started),
            (_starts("tool result: stop_helper"), '{"tool": "collect", "argument": "all"}'),
            (_starts("tool result: collect"), '{"final": "both stopped"}'),
        ],
    )

    result = asyncio.run(_run_with_helpers(RunRequest(conv, "coordinate the work")))

    assert result.reply == "both stopped"
    statuses = asyncio.run(
        _column("select status from tasks where conversation_id = %s", (conv,))
    )
    assert statuses == ["stopped", "stopped"]


def test_two_json_actions_in_one_reply_take_the_first():
    reply = activities._parse_reply(
        '{"tool": "get_tool_schema", "argument": "delegate"}\n'
        '{"tool": "get_tool_schema", "argument": "collect"}'
    )

    assert reply.kind == "tool"
    assert reply.tool == "get_tool_schema"
    assert reply.argument == "delegate"


def test_every_tool_spec_has_exactly_one_handler():
    from agent_service import workflow as workflow_module

    activity = {tool.name for tool in activities.TOOL_SPECS if tool.site == "activity"}
    flow = {tool.name for tool in activities.TOOL_SPECS if tool.site == "workflow"}

    assert activity == set(activities.ACTIVITY_TOOLS)
    assert flow == set(workflow_module.WORKFLOW_TOOL_NAMES)
    assert all(tool.schema for tool in activities.TOOL_SPECS)
    assert set(activities.NEEDS_APPROVAL) == {
        tool.name for tool in activities.TOOL_SPECS if tool.approval
    }
    for tool in activities.TOOL_SPECS:
        assert tool.name in activities.PROMPTS[activities.PROMPT_VERSION]["system"]


async def _task_status(conv: str):
    async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
        cursor = await conn.execute(
            "select status from tasks where conversation_id = %s", (conv,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


def test_a_turn_can_end_with_a_task_running(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_router(
        monkeypatch,
        [
            ("do the A work", '{"final": "A report"}'),
            ("coordinate the work", '{"tool": "delegate", "argument": "do the A work"}'),
            (_starts("tool result: delegate -> started"), '{"final": "started it"}'),
        ],
    )

    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with AsyncExitStack() as stack:
                for worker in _two_workers(env.client):
                    await stack.enter_async_context(worker)
                result = await env.client.execute_workflow(
                    RunWorkflow.run,
                    RunRequest(conv, "coordinate the work"),
                    id=f"turn:{uuid4().hex}",
                    task_queue=SERVICE_QUEUE,
                )
                for _ in range(100):
                    status = await _task_status(conv)
                    if status not in (None, "running"):
                        break
                    await asyncio.sleep(0.05)
                return result, status

    result, status = asyncio.run(scenario())

    assert result.reply == "started it"
    assert status == "done"
    assert asyncio.run(
        _scalar(
            "select count(*) from outbox where id = %s",
            (f"helper:local:{conv}:t1:done",),
        )
    ) == 1


def test_a_helper_report_starts_a_new_turn(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_router(
        monkeypatch,
        [(_starts("helper t1 finished:"), '{"final": "noted the report"}')],
    )
    envelope = Envelope(
        event_id=f"helper:local:{conv}:t1",
        type="agent.helper.completed",
        org_id="local",
        subject={"conversation_id": conv, "task_id": "t1"},
        payload={"report": "A report", "status": "done"},
    )

    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue=SERVICE_QUEUE,
                workflows=[RunWorkflow],
                activities=ACTIVITIES,
            ):
                started = await handle(env.client, envelope)
                return await started.result()

    assert asyncio.run(scenario()).reply == "noted the report"
    stored = next(
        entry["content"]
        for entry in transcript.load("local", conv)
        if entry["role"] == "user"
    )
    assert stored.startswith("helper t1 finished:")
    assert "<untrusted>" in stored
    assert "A report" in stored


def test_routine_helper_report_speaks_once_a_day(monkeypatch):
    conv = f"t-{uuid4().hex}"
    _fake_model(
        monkeypatch,
        '{"final": "noted"}',
        '{"final": "noted"}',
        '{"final": "hello"}',
    )
    first_id = f"turn:{uuid4().hex}"
    second_id = f"turn:{uuid4().hex}"
    user_id = f"turn:{uuid4().hex}"

    first = asyncio.run(
        _run(
            RunRequest(conv, "helper t1 finished: all good", kind="helper"),
            first_id,
        )
    )
    second = asyncio.run(
        _run(
            RunRequest(conv, "helper t2 finished: all good", kind="helper"),
            second_id,
        )
    )
    user = asyncio.run(_run(RunRequest(conv, "hello"), user_id))

    assert first.silent is False
    assert second.silent is True
    assert user.silent is False
    assert asyncio.run(
        _scalar("select count(*) from outbox where id = %s", (f"local:{first_id}:save",))
    ) == 1
    assert asyncio.run(
        _scalar("select count(*) from outbox where id = %s", (f"local:{second_id}:save",))
    ) == 0
    assert asyncio.run(
        _scalar("select count(*) from outbox where id = %s", (f"local:{user_id}:save",))
    ) == 1
    completed = json.loads(
        asyncio.run(
            _scalar(
                "select payload from outbox where id = %s",
                (f"run:{second_id}:completed",),
            )
        )
    )["payload"]
    assert completed["silent"] is True
    assert asyncio.run(
        _scalar("select count(*) from outbox where id = %s", (f"run:{first_id}:started",))
    ) == 1
    assert len(transcript.load("local", conv)) == 6


def test_a_failed_helper_report_speaks(monkeypatch):
    conv = f"t-{uuid4().hex}"
    run_id = f"turn:{uuid4().hex}"
    _fake_model(monkeypatch, '{"final": "I will check it"}')

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "insert into notifications (org_id, conversation_id, last_at)"
                " values ('local', %s, now())"
                " on conflict (org_id, conversation_id) do update set last_at = now()",
                (conv,),
            )

    asyncio.run(seed())
    result = asyncio.run(
        _run(
            RunRequest(conv, "helper t1 finished: it failed", kind="helper", failed=True),
            run_id,
        )
    )

    assert result.silent is False
    assert asyncio.run(
        _scalar("select count(*) from outbox where id = %s", (f"local:{run_id}:save",))
    ) == 1


def test_a_failed_turn_emits_run_failed(monkeypatch):
    conv = f"t-{uuid4().hex}"
    run_id = f"turn:{uuid4().hex}"
    _fake_model(monkeypatch)

    result = asyncio.run(_run(RunRequest(conv, "do it", max_steps=0), run_id))
    assert result.budget_exhausted is True
    assert "step budget" in result.reply

    assert asyncio.run(
        _scalar("select count(*) from outbox where id = %s", (f"run:{run_id}:started",))
    ) == 1
    assert asyncio.run(
        _scalar("select count(*) from outbox where id = %s", (f"run:{run_id}:failed",))
    ) == 1


def test_list_tasks_reports_status():
    conv = f"t-{uuid4().hex}"
    task_id = asyncio.run(
        activities.create_task("local", conv, "do the thing", "helper:x")
    )

    assert asyncio.run(activities.list_tasks("local", conv)) == "t1 running: do the thing"

    asyncio.run(activities.finish_task("local", conv, task_id, "done", "ok"))

    assert "t1 done: do the thing" in asyncio.run(activities.list_tasks("local", conv))


def test_a_failing_helper_leaves_a_task_for_the_reaper(monkeypatch):
    conv = f"t-{uuid4().hex}"
    fresh = f"t-{uuid4().hex}"

    def boom(last, payload):
        raise activities.ApplicationError("helper crashed", non_retryable=True)

    _fake_router(
        monkeypatch,
        [
            ("do the A work", boom),
            ("coordinate the work", '{"tool": "delegate", "argument": "do the A work"}'),
            (_starts("tool result: delegate -> started"), '{"final": "started it"}'),
        ],
    )

    result = asyncio.run(_run_with_helpers(RunRequest(conv, "coordinate the work")))

    assert result.reply == "started it"
    assert asyncio.run(
        _scalar("select status from tasks where conversation_id = %s", (conv,))
    ) == "running"

    asyncio.run(activities.create_task("local", fresh, "a fresh task", "helper:y"))

    async def age():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "update tasks set updated_at = now() - interval '5 hours'"
                " where conversation_id = %s",
                (conv,),
            )

    asyncio.run(age())
    asyncio.run(activities.reap_tasks())

    assert asyncio.run(
        _scalar("select status from tasks where conversation_id = %s", (conv,))
    ) == "failed"
    assert asyncio.run(
        _scalar("select report from tasks where conversation_id = %s", (conv,))
    ) == "helper did not report within its time limit"
    assert asyncio.run(
        _scalar(
            "select count(*) from outbox where id = %s",
            (f"helper:local:{conv}:t1:failed",),
        )
    ) == 1
    assert asyncio.run(
        _scalar("select status from tasks where conversation_id = %s", (fresh,))
    ) == "running"


def test_retention_windows_are_doubled():
    assert (
        maintenance.MESSAGE_DAYS,
        maintenance.MODEL_CALL_DAYS,
        maintenance.EFFECT_DAYS,
        maintenance.INBOX_DAYS,
        maintenance.OUTBOX_DAYS,
        maintenance.APPROVAL_DAYS,
        maintenance.REVIEW_DAYS,
        maintenance.TASK_DAYS,
        maintenance.NOTIFICATION_DAYS,
        maintenance.DELETION_DAYS,
    ) == (60, 60, 180, 180, 180, 730, 730, 180, 180, 730)


def test_purge_deletes_old_rows_and_keeps_new_ones():
    org = f"ret-{uuid4().hex}"
    conv = f"ret-{uuid4().hex}"
    old = f"ret-{uuid4().hex}"

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "insert into effects"
                " (token, kind, payload, org_id, conversation_id, created_at)"
                " values (%s, 'echo', 'x', %s, %s, now() - interval '181 days')",
                (old, org, conv),
            )
            await conn.execute(
                "insert into approvals"
                " (id, org_id, conversation_id, workflow_id, action, arguments,"
                "  status, created_at)"
                " values (%s, %s, %s, 'wf', 'send_email', 'a@b', 'approved',"
                "  now() - interval '731 days')",
                (old, org, conv),
            )
            await conn.execute(
                "insert into reviews"
                " (org_id, conversation_id, run_id, step, tool, argument, verdict,"
                "  reason, prompt_version, created_at)"
                " values (%s, %s, 'run', 0, 'send_email', 'a@b', 'allow', 'ok',"
                "  '1', now() - interval '731 days')",
                (org, conv),
            )
            await conn.execute(
                "insert into tasks"
                " (id, org_id, conversation_id, description, status,"
                "  helper_workflow_id, created_at)"
                " values (%s, %s, %s, 'old', 'done', 'h', now() - interval '181 days')",
                (old, org, conv),
            )
            await conn.execute(
                "insert into notifications (org_id, conversation_id, last_at)"
                " values (%s, %s, now() - interval '181 days')",
                (org, conv),
            )
            await conn.execute(
                "insert into inbox (event_id, org_id, received_at)"
                " values (%s, %s, now() - interval '181 days')",
                (old, org),
            )
            await conn.execute(
                "insert into outbox"
                " (id, topic, payload, org_id, conversation_id, created_at)"
                " values (%s, 'agent.messages', '{}', %s, %s,"
                "  now() - interval '181 days')",
                (old, org, conv),
            )
            await conn.execute(
                "insert into model_calls"
                " (org_id, conversation_id, seq, step, model, prompt_hash,"
                "  prompt_version, prompt_tokens, cache_hit, cache_miss,"
                "  completion_tokens, created_at)"
                " values (%s, %s, 1, 0, 'm', 'h', '1', 10, 1, 9, 2,"
                "  now() - interval '61 days')",
                (org, conv),
            )

    asyncio.run(seed())
    transcript.write_entry(org, conv, 1, 0, "user", "old")
    old_path = storage.LOCAL_ROOT / transcript._key(org, conv, 1)
    old_time = (datetime.now(timezone.utc) - timedelta(days=61)).timestamp()
    os.utime(old_path, (old_time, old_time))
    transcript.write_entry(org, conv, 2, 0, "user", "new")
    transcript.add_fact(org, conv, "kept", "user")
    transcript.add_note(org, conv, "stale scratch", "scratch-token")
    scratch_path = storage.LOCAL_ROOT / transcript._scratch_key(
        org, conv, "scratch-token"
    )
    os.utime(scratch_path, (old_time, old_time))
    counts = asyncio.run(maintenance.purge())

    assert counts.get("transcript", 0) >= 1
    assert counts.get("scratch", 0) >= 1
    assert counts.get("effects", 0) >= 1
    assert counts.get("approvals", 0) >= 1
    assert counts.get("reviews", 0) >= 1
    assert counts.get("tasks", 0) >= 1
    assert counts.get("notifications", 0) >= 1
    assert counts.get("inbox", 0) >= 1
    assert counts.get("outbox", 0) >= 1
    assert counts.get("model_calls", 0) >= 1
    assert [entry["content"] for entry in transcript.load(org, conv)] == ["new"]
    assert asyncio.run(
        _scalar("select count(*) from effects where token = %s", (old,))
    ) == 0
    assert asyncio.run(
        _scalar("select count(*) from approvals where id = %s", (old,))
    ) == 0
    assert asyncio.run(
        _scalar("select count(*) from reviews where conversation_id = %s", (conv,))
    ) == 0
    assert asyncio.run(
        _scalar("select count(*) from tasks where conversation_id = %s", (conv,))
    ) == 0
    assert asyncio.run(
        _scalar("select count(*) from notifications where conversation_id = %s", (conv,))
    ) == 0
    assert asyncio.run(
        _scalar("select count(*) from inbox where event_id = %s", (old,))
    ) == 0
    assert asyncio.run(
        _scalar("select count(*) from outbox where id = %s", (old,))
    ) == 0
    assert asyncio.run(
        _scalar("select count(*) from model_calls where conversation_id = %s", (conv,))
    ) == 0
    user_facts, _ = transcript.load_facts(org, conv)
    assert "kept" in user_facts
    assert transcript.load_scratch(org, conv, None) == []


def test_delete_conversation_scopes_rows_and_writes_audit():
    org = f"del-{uuid4().hex}"
    conv = f"del-{uuid4().hex}"
    other = f"del-{uuid4().hex}"
    token = f"del-{uuid4().hex}"

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "insert into conversations (org_id, conversation_id) values (%s, %s)",
                (org, conv),
            )
            await conn.execute(
                "insert into effects (token, kind, payload, org_id, conversation_id)"
                " values (%s, 'echo', 'x', %s, %s)",
                (token, org, conv),
            )
            await conn.execute(
                "insert into outbox (id, topic, payload, org_id, conversation_id)"
                " values (%s, 'agent.messages', '{}', %s, %s)",
                (token, org, conv),
            )
            await conn.execute(
                "insert into approvals"
                " (id, org_id, conversation_id, workflow_id, action, arguments)"
                " values (%s, %s, %s, 'wf', 'send_email', 'a@b')",
                (token, org, conv),
            )
            await conn.execute(
                "insert into reviews"
                " (org_id, conversation_id, run_id, step, tool, argument, verdict)"
                " values (%s, %s, 'run', 0, 'send_email', 'a@b', 'allow')",
                (org, conv),
            )
            await conn.execute(
                "insert into tasks"
                " (id, org_id, conversation_id, description, status, helper_workflow_id)"
                " values ('t1', %s, %s, 'x', 'done', 'h')",
                (org, conv),
            )
            await conn.execute(
                "insert into notifications (org_id, conversation_id) values (%s, %s)",
                (org, conv),
            )
            await conn.execute(
                "insert into model_calls"
                " (org_id, conversation_id, seq, step, model, prompt_hash,"
                "  prompt_tokens, cache_hit, cache_miss, completion_tokens)"
                " values (%s, %s, 1, 0, 'm', 'h', 1, 0, 1, 1)",
                (org, conv),
            )
            await conn.execute(
                "insert into routines (id, org_id, conversation_id, cron, text)"
                " values ('rt_del', %s, %s, '0 8 * * *', 'x')",
                (org, conv),
            )

    asyncio.run(seed())
    transcript.write_entry(org, conv, 1, 0, "user", "x")
    transcript.add_fact(org, conv, "x", "user")
    transcript.write_entry(org, other, 1, 0, "user", "y")
    counts = asyncio.run(maintenance.delete_scope(org, conv))

    assert counts["transcript"] == 2
    assert counts["effects"] == 1
    assert counts["outbox"] == 1
    assert counts["conversations"] == 1
    assert counts["routines"] == 1
    assert transcript.load(org, conv) == []
    assert transcript.load_facts(org, conv) == ([], [])
    assert [entry["content"] for entry in transcript.load(org, other)] == ["y"]
    assert asyncio.run(
        _scalar("select count(*) from deletions where org_id = %s and conversation_id = %s", (org, conv))
    ) == 1
    audit = json.loads(
        asyncio.run(
            _scalar(
                "select counts::text from deletions where org_id = %s and conversation_id = %s",
                (org, conv),
            )
        )
    )
    assert audit["transcript"] == 2


def test_delete_refuses_a_busy_conversation():
    org = f"busy-{uuid4().hex}"
    conv = f"busy-{uuid4().hex}"

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "insert into conversation_locks"
                " (org_id, conversation_id, workflow_id, expires_at)"
                " values (%s, %s, 'wf', now() + interval '1 hour')",
                (org, conv),
            )

    asyncio.run(seed())
    transcript.write_entry(org, conv, 1, 0, "user", "x")
    with pytest.raises(RuntimeError):
        asyncio.run(maintenance.delete_scope(org, conv))
    assert len(transcript.load(org, conv)) == 1


def test_delete_org_removes_all_conversations():
    org = f"orgdel-{uuid4().hex}"

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "insert into inbox (event_id, org_id) values (%s, %s)",
                (f"evt-{uuid4().hex}", org),
            )

    asyncio.run(seed())
    transcript.write_entry(org, "a", 1, 0, "user", "x")
    transcript.write_entry(org, "b", 1, 0, "user", "y")
    counts = asyncio.run(maintenance.delete_scope(org, None))

    assert counts["transcript"] == 2
    assert counts["inbox"] == 1
    assert transcript.load(org, "a") == []
    assert transcript.load(org, "b") == []
    assert asyncio.run(
        _scalar("select conversation_id from deletions where org_id = %s", (org,))
    ) == ""


def test_health_endpoints():
    server = start_health_server(0, "test")
    port = server.server_address[1]
    try:
        alive = urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5)
        ready = urllib.request.urlopen(f"http://127.0.0.1:{port}/readyz", timeout=5)
        assert alive.status == 200
        assert alive.read() == b"test alive"
        assert ready.status == 200
        assert ready.read() == b"test ready"
        metrics = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/metrics", timeout=5
        )
        assert metrics.status == 200
        body = metrics.read().decode()
        assert "agent_run_success_rate" in body
        assert "agent_turn_latency_seconds" in body
        assert "agent_cache_hit_ratio" in body
        assert "agent_tokens_total" in body
        assert "agent_consumer_lag_seconds" in body
    finally:
        server.shutdown()
        server.server_close()


def test_routine_turn_over_quota_is_dropped():
    org = f"quota-{uuid4().hex}"
    conv = f"quota-{uuid4().hex}"
    cap_conv = f"quota-{uuid4().hex}"

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "insert into conversation_locks"
                " (org_id, conversation_id, workflow_id, expires_at)"
                " values (%s, %s, 'wf', now() + interval '1 hour'),"
                " (%s, %s, 'wf2', now() + interval '1 hour')",
                (org, conv, org, cap_conv),
            )

    asyncio.run(seed())

    interactive = Envelope(
        event_id=f"int-{uuid4().hex}",
        type=SEND_MESSAGE,
        org_id=org,
        subject={"conversation_id": conv},
        payload={"text": "hi"},
        priority="interactive",
    )
    routine = Envelope(
        event_id=f"rout-{uuid4().hex}",
        type=SEND_MESSAGE,
        org_id=org,
        subject={"conversation_id": conv},
        payload={"text": "routine"},
        priority="routine",
    )

    # With two active runs, routine (cap 1) is over quota; interactive is never dropped.
    assert asyncio.run(consumer_module._over_quota(routine)) is True
    assert asyncio.run(consumer_module._over_quota(interactive)) is False


def test_dead_letter_wraps_the_raw_event():
    class Producer:
        def __init__(self):
            self.sent = []

        async def send_and_wait(self, topic, value):
            self.sent.append((topic, value))

    class Message:
        value = b"not json"

    producer = Producer()
    asyncio.run(
        consumer_module._dead_letter(producer, Message(), ValueError("bad event"))
    )

    topic, value = producer.sent[0]
    data = json.loads(value)
    assert topic == consumer_module.DLQ_TOPIC
    assert data["error"] == "ValueError: bad event"
    assert data["event"]["raw"] == "not json"


class _FakeHandle:
    def __init__(self) -> None:
        self.paused = 0
        self.unpaused = 0
        self.deleted = 0

    async def pause(self) -> None:
        self.paused += 1

    async def unpause(self) -> None:
        self.unpaused += 1

    async def delete(self) -> None:
        self.deleted += 1

    async def update(self, updater) -> None:
        updater(None)


class _FakeScheduleClient:
    def __init__(self) -> None:
        self.created: dict = {}
        self.handles: dict = {}

    async def create_schedule(self, schedule_id, schedule):
        self.created[schedule_id] = schedule
        handle = _FakeHandle()
        self.handles[schedule_id] = handle
        return handle

    def get_schedule_handle(self, schedule_id):
        return self.handles.setdefault(schedule_id, _FakeHandle())


def test_create_routine_writes_row_and_schedule():
    org = f"rt-{uuid4().hex}"
    conv = f"rt-{uuid4().hex}"
    client = _FakeScheduleClient()

    routine_id = asyncio.run(
        routines.create_routine(
            org, conv, "0 8 * * *", "check the inbox", "Africa/Nairobi", client=client
        )
    )

    assert routine_id.startswith("rt_")
    row = asyncio.run(routines.get_routine(routine_id))
    assert row is not None
    assert row["cron"] == "0 8 * * *"
    assert row["enabled"] is True
    schedule = client.created[f"routine:{routine_id}"]
    request = schedule.action.args[0]
    assert request.kind == "routine"
    assert request.routine_id == routine_id
    assert request.conversation_id == conv

    asyncio.run(routines.set_enabled(routine_id, False, client=client))
    assert asyncio.run(routines.get_routine(routine_id))["enabled"] is False
    asyncio.run(routines.set_enabled(routine_id, True, client=client))
    asyncio.run(routines.delete_routine(routine_id, client=client))
    assert asyncio.run(routines.get_routine(routine_id)) is None


def test_create_routine_rejects_an_unknown_timezone():
    with pytest.raises(ValueError):
        asyncio.run(
            routines.create_routine(
                "local", "c", "0 8 * * *", "x", "Mars/Olympus"
            )
        )


def test_a_routine_cannot_run_an_irreversible_tool(monkeypatch):
    org = "local"
    conv = f"rt-{uuid4().hex}"
    routine_id = f"rt_{uuid4().hex}"

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "insert into routines"
                " (id, org_id, conversation_id, cron, text)"
                " values (%s, %s, %s, '0 8 * * *', 'send the email')",
                (routine_id, org, conv),
            )

    asyncio.run(seed())
    _fake_model(
        monkeypatch,
        '{"tool": "send_email", "argument": "a@b"}',
        '{"final": "I cannot send it"}',
    )

    result = asyncio.run(
        _run(
            RunRequest(
                conv, "send the email", org_id=org, kind="routine", routine_id=routine_id
            ),
            f"turn:{uuid4().hex}",
        )
    )

    assert result.reply == "I cannot send it"
    assert asyncio.run(
        _scalar("select count(*) from approvals where conversation_id = %s", (conv,))
    ) == 0
    assert asyncio.run(
        _scalar(
            "select count(*) from effects"
            " where conversation_id = %s and kind = 'send_email'",
            (conv,),
        )
    ) == 0
    step = next(
        (
            entry["content"]
            for entry in transcript.load(org, conv)
            if entry["role"] == "tool"
        ),
        "",
    )
    assert "routine turns cannot run irreversible tools" in step


def test_a_disabled_routine_does_not_run(monkeypatch):
    org = "local"
    conv = f"rt-{uuid4().hex}"
    routine_id = f"rt_{uuid4().hex}"

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "insert into routines"
                " (id, org_id, conversation_id, cron, text, enabled)"
                " values (%s, %s, %s, '0 8 * * *', 'x', false)",
                (routine_id, org, conv),
            )

    asyncio.run(seed())
    _fake_model(monkeypatch)

    result = asyncio.run(
        _run(
            RunRequest(
                conv, "x", org_id=org, kind="routine", routine_id=routine_id
            ),
            f"turn:{uuid4().hex}",
        )
    )

    assert result.silent is True
    assert transcript.load(org, conv) == []


def test_a_routine_turn_always_speaks():
    assert asyncio.run(should_speak("local", "c", "routine", False, "no question")) is True


def test_transcript_is_files_per_turn():
    conv = f"file-{uuid4().hex}"
    transcript.write_entry("local", conv, 0, 0, "user", "the code is 1234")
    transcript.write_entry("local", conv, 0, 1, "assistant", "noted")
    transcript.write_entry("local", conv, 1, 0, "user", "second turn")
    transcript.write_entry("local", conv, 1, 2, "assistant", "noted")
    transcript.write_entry("local", conv, 1, 2, "assistant", "different")

    entries = transcript.load("local", conv)
    assert [(e["seq"], e["step"], e["role"]) for e in entries] == [
        (0, 0, "user"),
        (0, 1, "assistant"),
        (1, 0, "user"),
        (1, 2, "assistant"),
    ]
    assert entries[-1]["content"] == "noted"
    assert max(e["seq"] for e in entries) == 1
    assert transcript.search("local", conv, "CODE")[0]["content"] == "the code is 1234"

    folder = storage.LOCAL_ROOT / transcript._prefix("local", conv)
    assert len(list(folder.glob("*.jsonl"))) == 2

    transcript.delete_scope("local", conv)
    assert transcript.load("local", conv) == []


def test_memory_files_hold_profile_scratch_and_summary():
    conv = f"mem-{uuid4().hex}"
    transcript.add_fact("local", conv, "likes tea", "user")
    transcript.add_fact("local", conv, "likes tea", "user")
    transcript.add_fact("local", conv, "tool fact", "tool")
    transcript.add_note("local", conv, "scratch note", "note-token")
    transcript.add_note("local", conv, "scratch note", "note-token")
    transcript.write_summary("local", conv, "the summary", 3)

    user, tool = transcript.load_facts("local", conv)
    assert user == ["likes tea"]
    assert tool == ["tool fact"]
    assert transcript.load_scratch("local", conv, None)[0]["content"] == "scratch note"
    assert transcript.load_summary("local", conv) == ("the summary", 3)
    assert (storage.LOCAL_ROOT / transcript._profile_key("local", conv)).is_file()
    assert (storage.LOCAL_ROOT / transcript._tool_facts_key("local", conv)).is_file()
    assert (storage.LOCAL_ROOT / transcript._summary_key("local", conv)).is_file()

    transcript.delete_scope("local", conv)
    assert transcript.load_facts("local", conv) == ([], [])
    assert transcript.load_scratch("local", conv, None) == []
    assert transcript.load_summary("local", conv) == ("", -1)


def test_local_artifact_roundtrip_and_scope(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)
    org = f"art-{uuid4().hex}"
    conv = f"art-{uuid4().hex}"

    artifact_id = storage.put(org, conv, "note.txt", "text/plain", b"hello")
    meta, data = storage.get(artifact_id, org, conv)
    assert data == b"hello"
    assert meta["name"] == "note.txt"
    with pytest.raises(storage.ArtifactNotFound):
        storage.get(artifact_id, org, "other")

    storage.delete_objects(org, conv)
    with pytest.raises(storage.ArtifactNotFound):
        storage.get(artifact_id, org, conv)

    async def clean():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute("delete from artifacts where id = %s", (artifact_id,))

    asyncio.run(clean())


def test_artifact_dedupes_by_content(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)
    org = f"art-{uuid4().hex}"
    conv = f"art-{uuid4().hex}"

    first = storage.put(org, conv, "a.txt", "text/plain", b"same bytes")
    second = storage.put(org, conv, "b.txt", "text/plain", b"same bytes")
    assert first == second

    storage.delete_objects(org, conv)

    async def clean():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute("delete from artifacts where org_id = %s", (org,))

    asyncio.run(clean())


def test_s3_key_layout(monkeypatch):
    class FakeS3:
        def __init__(self):
            self.objects = {}
            self.deleted = []

        def put_object(self, Bucket, Key, Body, ContentType):
            self.objects[Key] = bytes(Body)

        def get_object(self, Bucket, Key):
            return {"Body": io.BytesIO(self.objects[Key])}

        def delete_objects(self, Bucket, Delete):
            self.deleted += [item["Key"] for item in Delete["Objects"]]

    fake = FakeS3()
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setattr(storage, "_s3_client", lambda: fake)
    org = f"art-{uuid4().hex}"
    conv = f"art-{uuid4().hex}"

    artifact_id = storage.put(org, conv, "a.txt", "text/plain", b"hello")
    sha = hashlib.sha256(b"hello").hexdigest()
    key = f"artifacts/{storage._safe(org)}/{storage._safe(conv)}/{sha}"
    assert key in fake.objects
    assert storage.get(artifact_id, org, conv)[1] == b"hello"

    storage.delete_objects(org, conv)
    assert key in fake.deleted

    async def clean():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute("delete from artifacts where id = %s", (artifact_id,))

    asyncio.run(clean())


def test_delete_scope_removes_artifacts(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)
    org = f"artdel-{uuid4().hex}"
    conv = f"artdel-{uuid4().hex}"
    artifact_id = storage.put(org, conv, "a.txt", "text/plain", b"hello")

    counts = asyncio.run(maintenance.delete_scope(org, conv))

    assert counts["artifacts"] == 1
    assert asyncio.run(
        _scalar("select count(*) from artifacts where id = %s", (artifact_id,))
    ) == 0
    with pytest.raises(storage.ArtifactNotFound):
        storage.get(artifact_id, org, conv)


def test_purge_removes_old_artifacts(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)
    org = f"artold-{uuid4().hex}"
    conv = f"artold-{uuid4().hex}"
    artifact_id = storage.put(org, conv, "a.txt", "text/plain", b"hello")

    async def age():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "update artifacts set created_at = now() - interval '181 days'"
                " where id = %s",
                (artifact_id,),
            )

    asyncio.run(age())
    counts = asyncio.run(maintenance.purge())

    assert counts.get("artifacts", 0) >= 1
    assert asyncio.run(
        _scalar("select count(*) from artifacts where id = %s", (artifact_id,))
    ) == 0


def test_a_long_turn_continues_as_new(monkeypatch):
    conv = f"long-{uuid4().hex}"
    run_id = f"turn:{uuid4().hex}"
    _fake_model(
        monkeypatch,
        *(['{"tool": "echo", "argument": "x"}'] * 25 + ['{"final": "done"}']),
    )
    monkeypatch.setattr(activities, "_summarize", lambda text: "working summary")

    result = asyncio.run(_run(RunRequest(conv, "keep going"), run_id))

    assert result.reply == "done"
    assert result.steps == 26
    assert asyncio.run(
        _scalar(
            "select count(*) from outbox where id = %s",
            (f"run:{run_id}:progress:20",),
        )
    ) == 1
    _, seq, step = transcript.load_working("local", conv)
    assert seq == 0
    assert step > 0


def test_the_plan_blocks_a_final_until_it_is_checked(monkeypatch):
    conv = f"plan-{uuid4().hex}"
    _fake_model(
        monkeypatch,
        '{"tool": "update_plan", "argument": "- [ ] a\\n- [ ] b"}',
        '{"final": "done"}',
        '{"tool": "update_plan", "argument": "- [x] a\\n- [x] b"}',
        '{"final": "done"}',
    )

    result = asyncio.run(_run(RunRequest(conv, "do the plan"), f"turn:{uuid4().hex}"))

    assert result.reply == "done"
    assert result.steps == 4
    assert transcript.load_plan("local", conv).count("- [ ]") == 0


def test_the_token_budget_returns_a_final(monkeypatch):
    conv = f"budget-{uuid4().hex}"
    _fake_model(
        monkeypatch,
        '{"tool": "echo", "argument": "one"}',
        '{"tool": "echo", "argument": "two"}',
        '{"final": "never reached"}',
    )

    result = asyncio.run(
        _run(
            RunRequest(conv, "spend", max_steps=10, max_tokens=20),
            f"turn:{uuid4().hex}",
        )
    )

    assert result.budget_exhausted is True
    assert "token budget" in result.reply


def test_a_stop_signal_ends_the_turn(monkeypatch):
    conv = f"stop-{uuid4().hex}"
    run_id = f"turn:{uuid4().hex}"
    _fake_model(monkeypatch, *(['{"tool": "echo", "argument": "x"}'] * 200))

    async def scenario():
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[RunWorkflow],
                activities=ACTIVITIES,
            ):
                handle = await env.client.start_workflow(
                    RunWorkflow.run,
                    RunRequest(conv, "stop me"),
                    id=run_id,
                    task_queue=TASK_QUEUE,
                )
                await handle.signal("stop", "test stop")
                return await handle.result()

    result = asyncio.run(scenario())

    assert result.stopped is True
    assert result.reply == "Stopped at your request."


def test_a_new_user_message_stops_the_active_run():
    conv = f"preempt-{uuid4().hex}"
    captured: list[tuple[str, str]] = []

    class Handle:
        async def signal(self, name: str, argument: str) -> None:
            captured.append((name, argument))

    class Client:
        def get_workflow_handle(self, workflow_id: str):
            assert workflow_id == "turn:old"
            return Handle()

    async def seed():
        async with await psycopg.AsyncConnection.connect(activities._dsn()) as conn:
            await conn.execute(
                "insert into conversation_locks"
                " (org_id, conversation_id, workflow_id, expires_at)"
                " values ('local', %s, 'turn:old', now() + interval '1 hour')",
                (conv,),
            )

    asyncio.run(seed())
    envelope = Envelope(
        event_id=f"e-{uuid4().hex}",
        type=SEND_MESSAGE,
        org_id="local",
        subject={"conversation_id": conv},
        payload={"text": "new message"},
    )

    asyncio.run(consumer_module._stop_active(Client(), envelope))

    assert captured == [("stop", "superseded by a new user message")]


def test_repeated_tool_calls_are_interrupted(monkeypatch):
    conv = f"stuck-{uuid4().hex}"
    _fake_model(
        monkeypatch,
        '{"tool": "echo", "argument": "same"}',
        '{"tool": "echo", "argument": "same"}',
        '{"tool": "echo", "argument": "same"}',
        '{"final": "changed approach"}',
    )

    result = asyncio.run(_run(RunRequest(conv, "do not loop"), f"turn:{uuid4().hex}"))

    assert result.reply == "changed approach"
    assert result.steps == 4
