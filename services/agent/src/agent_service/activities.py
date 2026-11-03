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

SYSTEM = """You are an agent on a server. You have two tools.
Reply with one JSON object and nothing else.
Do not call a tool that already succeeded in this conversation.
echo: {"tool": "echo", "argument": "<text>"}
send_email: {"tool": "send_email", "argument": "<address> <text>"}
Answer: {"final": "<text>"}
"""

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


async def next_seq(conn: psycopg.AsyncConnection, org_id: str, conversation_id: str) -> int:
    """The next turn number. Runs on the caller's connection, inside its lock."""
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


@activity.defn
async def call_model(step: int, history: list[str]) -> ModelReply:
    """Ask the real model what to do next.

    Sources: talk §04 (the model selects a tool call), talk §05 (a stable
    system prompt keeps the prefix cacheable), lesson 01.
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
async def load_history(org_id: str, conversation_id: str) -> list[str]:
    """The conversation so far, oldest first.

    Sources: talk §05 (memory is layered), lesson 07 (three layers).
    """
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select role, content from messages"
            " where org_id = %s and conversation_id = %s"
            " order by seq, step",
            (org_id, conversation_id),
        )
        return [f"{role}: {content}" async for role, content in cursor]


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

    Sources: talk §04 (the harness, not the model, executes tools); EDA §5
    (every effect carries a token, so a retry is safe).
    """
    if name in ("echo", "send_email"):
        async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
            await _claim(conn, effect_token, name, argument)
        return ToolResult(ok=True, output=argument)
    return ToolResult(ok=False, output=f"unknown tool: {name}")
