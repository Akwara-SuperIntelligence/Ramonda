"""Activities: every effect a turn performs.

Sources
    talk §03 — the agent loop is a model calling tools, run on a server
    talk §04 — the harness executes the tool call; the model only names it
    talk §05 — a stable system prompt keeps the prefix cacheable
    lesson 02 — write the intent down before the effect

Delta
    Effects and messages live in Postgres. A retried activity is a no-op
    because the effect token is the primary key of the effects table.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from temporalio import activity

from agent_service.events import (
    APPROVAL_REQUESTED,
    APPROVAL_TOPIC,
    MESSAGE_COMPOSED,
    MESSAGE_TOPIC,
    Envelope,
)

# One line of policy. Add a tool here when it can do something irreversible.
NEEDS_APPROVAL = {"send_email": True}

# Ordered sections: move the prefix and the provider cache is lost.
RULES = """You are an agent on a server. You have these tools: echo, send_email, read_file.
Reply with one JSON object and nothing else.
Do not call a tool that already succeeded in this conversation."""

TOOLS = """echo: {"tool": "echo", "argument": "<text>"}
send_email: {"tool": "send_email", "argument": "<address> <text>"}
read_file: {"tool": "read_file", "argument": "<name from a stored output>"}
Answer: {"final": "<text>"}"""

SYSTEM = RULES + "\n\n" + TOOLS
PROMPT_HASH = hashlib.sha256(SYSTEM.encode()).hexdigest()[:12]

COMPACT_AFTER = 20
KEEP_TURNS = 6
ARTIFACTS = Path(".agent/artifacts")
SIZE_LIMIT = 2000

# Tenant now arrives in the request; the column existed from day one.


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


def _dsn() -> str:
    return os.environ.get(
        "DATABASE_URL", "postgresql://ramonda:ramonda@127.0.0.1:5432/agent"
    )


async def _claim(conn: psycopg.AsyncConnection, token: str, kind: str, payload: str) -> bool:
    """Insert the effect once. True the first time; False on any repeat."""
    cursor = await conn.execute(
        "insert into effects (token, kind, payload) values (%s, %s, %s)"
        " on conflict do nothing returning token",
        (token, kind, payload),
    )
    return await cursor.fetchone() is not None


@activity.defn
async def acquire_lock(org_id: str, conversation_id: str, workflow_id: str) -> bool:
    """Take the conversation lock, or take over an expired one.

    TTL is the safety net: a terminated workflow never releases its row.
    """
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "insert into conversation_locks (org_id, conversation_id, workflow_id, expires_at)"
            " values (%s, %s, %s, now() + interval '1 hour')"
            " on conflict (org_id, conversation_id) do update"
            " set workflow_id = excluded.workflow_id, expires_at = excluded.expires_at"
            " where conversation_locks.expires_at < now()"
            " returning workflow_id",
            (org_id, conversation_id, workflow_id),
        )
        return await cursor.fetchone() is not None


@activity.defn
async def release_lock(org_id: str, conversation_id: str, workflow_id: str) -> None:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        await conn.execute(
            "delete from conversation_locks"
            " where org_id = %s and conversation_id = %s and workflow_id = %s",
            (org_id, conversation_id, workflow_id),
        )


@activity.defn
async def next_turn(org_id: str, conversation_id: str) -> int:
    """The next turn number. Only read while the conversation lock is held."""
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select coalesce(max(seq) + 1, 0) from messages"
            " where org_id = %s and conversation_id = %s",
            (org_id, conversation_id),
        )
        return (await cursor.fetchone())[0]


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


def _summarize(text: str) -> str:
    body = _post(
        {
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Summarise this conversation. Keep facts, decisions, names, "
                        "and open tasks. Be brief."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0,
        }
    )
    return body["choices"][0]["message"]["content"].strip()


@activity.defn
async def call_model(
    org_id: str, conversation_id: str, seq: int, step: int, history: list[str]
) -> ModelReply:
    """Ask the real model what to do next, and record what it cost.

    Sources: talk §04 (the model selects a tool call), talk §05 (a stable
    system prompt keeps the prefix cacheable), lesson 01.
    """
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    body = _post(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": "\n".join(history)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
    )
    usage = body.get("usage") or {}
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        await conn.execute(
            "insert into model_calls (org_id, conversation_id, seq, step, model,"
            " prompt_hash, prompt_tokens, cache_hit, cache_miss, completion_tokens)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " on conflict (org_id, conversation_id, seq, step) do update set"
            " model = excluded.model, prompt_hash = excluded.prompt_hash,"
            " prompt_tokens = excluded.prompt_tokens, cache_hit = excluded.cache_hit,"
            " cache_miss = excluded.cache_miss,"
            " completion_tokens = excluded.completion_tokens",
            (
                org_id,
                conversation_id,
                seq,
                step,
                model,
                PROMPT_HASH,
                usage.get("prompt_tokens", 0),
                usage.get("prompt_cache_hit_tokens", 0),
                usage.get("prompt_cache_miss_tokens", 0),
                usage.get("completion_tokens", 0),
            ),
        )
    return _parse_reply(body["choices"][0]["message"]["content"])


@activity.defn
async def compact(org_id: str, conversation_id: str) -> None:
    """Summarise old turns once the un-summarised tail grows.

    Sources: talk §05 — compaction while the cache is warm.
    """
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select summary, summary_seq from conversations"
            " where org_id = %s and conversation_id = %s",
            (org_id, conversation_id),
        )
        row = await cursor.fetchone()
        summary, summary_seq = row if row else ("", -1)

        cursor = await conn.execute(
            "select count(*), coalesce(max(seq), -1) from messages"
            " where org_id = %s and conversation_id = %s and seq > %s",
            (org_id, conversation_id, summary_seq),
        )
        count, max_seq = await cursor.fetchone()
        cutoff = max_seq - KEEP_TURNS
        if count <= COMPACT_AFTER or cutoff <= summary_seq:
            return

        cursor = await conn.execute(
            "select role, content from messages"
            " where org_id = %s and conversation_id = %s and seq > %s and seq <= %s"
            " order by seq, step",
            (org_id, conversation_id, summary_seq, cutoff),
        )
        lines = [f"{role}: {content}" async for role, content in cursor]
        text = (f"Previous summary:\n{summary}\n\n" if summary else "") + "\n".join(lines)
        new_summary = _summarize(text)
        await conn.execute(
            "insert into conversations (org_id, conversation_id, summary, summary_seq)"
            " values (%s, %s, %s, %s)"
            " on conflict (org_id, conversation_id) do update set"
            " summary = excluded.summary, summary_seq = excluded.summary_seq",
            (org_id, conversation_id, new_summary, cutoff),
        )


@activity.defn
async def load_history(org_id: str, conversation_id: str) -> list[str]:
    """The conversation so far, oldest first, with any summary first.

    Sources: talk §05 (memory is layered), lesson 07 (three layers).
    """
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select summary, summary_seq from conversations"
            " where org_id = %s and conversation_id = %s",
            (org_id, conversation_id),
        )
        row = await cursor.fetchone()
        summary, summary_seq = row if row else ("", -1)
        cursor = await conn.execute(
            "select role, content from messages"
            " where org_id = %s and conversation_id = %s and seq > %s"
            " order by seq, step",
            (org_id, conversation_id, summary_seq),
        )
        lines = [f"{role}: {content}" async for role, content in cursor]
        return ([f"summary: {summary}"] if summary else []) + lines


@activity.defn
async def save_tool_step(
    org_id: str, conversation_id: str, seq: int, step: int, content: str
) -> None:
    """Record what the tool actually did, so the transcript is honest.

    Sources: talk §05 (files and logs are memory), lesson 07.
    """
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        await conn.execute(
            "insert into messages (org_id, conversation_id, seq, step, role, content)"
            " values (%s, %s, %s, %s, 'tool', %s) on conflict do nothing",
            (org_id, conversation_id, seq, step, content),
        )


@activity.defn
async def send_user(
    org_id: str,
    conversation_id: str,
    seq: int,
    assistant_step: int,
    user_text: str,
    text: str,
    effect_token: str,
) -> None:
    """Store the turn and queue the message, atomically.

    Sources: talk §04 (one tool crosses the client boundary); EDA §4.2
    (`agent.message.composed`), EDA §5 (outbox, not a dual write); lesson 07.
    """
    envelope = Envelope(
        event_id=effect_token,
        type=MESSAGE_COMPOSED,
        org_id=org_id,
        subject={"conversation_id": conversation_id},
        payload={"text": text},
        occurred_at=datetime.now(timezone.utc).isoformat(),
    )
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.transaction():
            if not await _claim(conn, effect_token, "turn", user_text):
                return
            await conn.execute(
                "insert into messages (org_id, conversation_id, seq, step, role, content)"
                " values (%s, %s, %s, 0, 'user', %s), (%s, %s, %s, %s, 'assistant', %s)"
                " on conflict do nothing",
                (org_id, conversation_id, seq, user_text,
                 org_id, conversation_id, seq, assistant_step, text),
            )
            await conn.execute(
                "insert into outbox (id, topic, payload) values (%s, %s, %s)",
                (effect_token, MESSAGE_TOPIC, envelope.to_json().decode()),
            )


@activity.defn
async def request_approval(
    org_id: str,
    conversation_id: str,
    workflow_id: str,
    action: str,
    arguments: str,
    approval_id: str,
) -> None:
    """Ask a human, and queue the request as an event.

    Sources: talk §04 (draft, ask, then act); lesson 09 (three guards).
    """
    envelope = Envelope(
        event_id=approval_id,
        type=APPROVAL_REQUESTED,
        org_id=org_id,
        subject={"conversation_id": conversation_id, "workflow_id": workflow_id},
        payload={"action": action, "arguments": arguments},
        occurred_at=datetime.now(timezone.utc).isoformat(),
    )
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.transaction():
            await conn.execute(
                "insert into approvals"
                " (id, org_id, conversation_id, workflow_id, action, arguments)"
                " values (%s, %s, %s, %s, %s, %s) on conflict do nothing",
                (approval_id, org_id, conversation_id, workflow_id, action, arguments),
            )
            await conn.execute(
                "insert into outbox (id, topic, payload) values (%s, %s, %s)"
                " on conflict do nothing",
                (approval_id, APPROVAL_TOPIC, envelope.to_json().decode()),
            )


@activity.defn
async def expire_approval(approval_id: str) -> None:
    """The deadline passed. Record it; the run continues without the effect."""
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        await conn.execute(
            "update approvals set status = 'expired', resolved_at = now()"
            " where id = %s and status = 'pending'",
            (approval_id,),
        )


@activity.defn
async def run_tool(name: str, argument: str, effect_token: str) -> ToolResult:
    """Execute one tool call, at most once per token.

    Sources: talk §04 (the harness, not the model, executes tools); talk §05
    (long output to a file, the path into context); EDA §5 (effect tokens).
    """
    if name == "read_file":
        path = ARTIFACTS / Path(argument).name
        if not path.is_file():
            return ToolResult(ok=False, output=f"no such file: {argument}")
        return ToolResult(ok=True, output=path.read_text()[:4000])

    if name not in ("echo", "send_email"):
        return ToolResult(ok=False, output=f"unknown tool: {name}")

    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        await _claim(conn, effect_token, name, argument)

    if len(argument) > SIZE_LIMIT:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        stored = hashlib.sha256(effect_token.encode()).hexdigest()[:16] + ".txt"
        (ARTIFACTS / stored).write_text(argument)
        output = argument[:500] + f"... [stored: {stored}] ({len(argument)} chars)"
    else:
        output = argument
    return ToolResult(ok=True, output=output)
