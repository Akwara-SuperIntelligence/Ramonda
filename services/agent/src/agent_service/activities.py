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
from pathlib import Path

import psycopg
from temporalio import activity

SYSTEM = """You are an agent on a server. You have one tool: echo.
Reply with one JSON object and nothing else.
Call the tool: {"tool": "echo", "argument": "<text>"}
Answer: {"final": "<text>"}
"""

# shortcut: one tenant until the edge supplies org_id; the column exists now.
ORG_ID = os.environ.get("AGENT_ORG_ID", "local")


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


async def next_seq(conversation_id: str) -> int:
    """The next turn number for a conversation. Read by the caller, not the workflow."""
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select coalesce(max(seq) + 1, 0) from messages"
            " where org_id = %s and conversation_id = %s",
            (ORG_ID, conversation_id),
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
async def load_history(conversation_id: str) -> list[str]:
    """The conversation so far, oldest first.

    Sources: talk §05 (memory is layered), lesson 07 (three layers).
    """
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select role, content from messages"
            " where org_id = %s and conversation_id = %s"
            " order by seq, case role when 'user' then 0 else 1 end",
            (ORG_ID, conversation_id),
        )
        return [f"{role}: {content}" async for role, content in cursor]


@activity.defn
async def save_turn(
    conversation_id: str, seq: int, user_text: str, assistant_text: str, effect_token: str
) -> None:
    """Append one turn exactly once.

    Sources: talk §03 (state is persisted on the server), lesson 07.
    """
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.transaction():
            if not await _claim(conn, effect_token, "turn", user_text):
                return
            await conn.execute(
                "insert into messages (org_id, conversation_id, seq, role, content)"
                " values (%s, %s, %s, 'user', %s), (%s, %s, %s, 'assistant', %s)"
                " on conflict do nothing",
                (ORG_ID, conversation_id, seq, user_text,
                 ORG_ID, conversation_id, seq, assistant_text),
            )


@activity.defn
async def run_tool(name: str, argument: str, effect_token: str) -> ToolResult:
    """Execute one tool call, at most once per token.

    Sources: talk §04 (the harness, not the model, executes tools); EDA §5
    (every effect carries a token, so a retry is safe).
    """
    if name == "echo":
        async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
            await _claim(conn, effect_token, name, argument)
        return ToolResult(ok=True, output=argument)
    return ToolResult(ok=False, output=f"unknown tool: {name}")
