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
from temporalio.exceptions import ApplicationError

from agent_service.events import (
    APPROVAL_REQUESTED,
    APPROVAL_TOPIC,
    HELPER_COMPLETED,
    HELPERS_TOPIC,
    MESSAGE_COMPOSED,
    MESSAGE_TOPIC,
    Envelope,
)

@dataclass(frozen=True)
class ToolSpec:
    """One tool: the name the model says, its schema, its policy, where it runs."""

    name: str
    schema: str
    approval: bool = False
    site: str = "activity"  # "activity" for effects, "workflow" for control flow


# Single source. The prompt, the schema lookup, and the policy are built from it.
TOOL_SPECS = [
    ToolSpec("echo", 'echo: {"tool": "echo", "argument": "<text>"}'),
    ToolSpec(
        "send_email",
        'send_email: {"tool": "send_email", "argument": "<address> <text>"}',
        approval=True,
    ),
    ToolSpec(
        "read_file",
        'read_file: {"tool": "read_file", "argument": "<name from a stored output>"}',
    ),
    ToolSpec(
        "get_tool_schema",
        'get_tool_schema: {"tool": "get_tool_schema", "argument": "<tool name>"}',
    ),
    ToolSpec("remember", 'remember: {"tool": "remember", "argument": "<durable fact>"}'),
    ToolSpec("note", 'note: {"tool": "note", "argument": "<temporary note>"}'),
    ToolSpec("recall", 'recall: {"tool": "recall", "argument": "<search text>"}'),
    ToolSpec("read_skill", 'read_skill: {"tool": "read_skill", "argument": "<skill name>"}'),
    ToolSpec(
        "delegate",
        'delegate: {"tool": "delegate", "argument": "<a self-contained task>"}',
        site="workflow",
    ),
    ToolSpec(
        "collect",
        'collect: {"tool": "collect", "argument": "<helper id or all>"}',
        site="workflow",
    ),
    ToolSpec("helpers", 'helpers: {"tool": "helpers", "argument": ""}', site="workflow"),
    ToolSpec(
        "message_helper",
        'message_helper: {"tool": "message_helper", "argument": "<helper id> <message>"}',
        site="workflow",
    ),
    ToolSpec(
        "stop_helper",
        'stop_helper: {"tool": "stop_helper", "argument": "<helper id>"}',
        site="workflow",
    ),
]

TOOL_NAMES = ", ".join(tool.name for tool in TOOL_SPECS)
TOOL_SCHEMAS = {tool.name: tool.schema for tool in TOOL_SPECS}
NEEDS_APPROVAL = {tool.name: True for tool in TOOL_SPECS if tool.approval}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


# Frozen. Do not edit: conversations pinned to this version must keep it.
V1_RULES = """You are an agent on a server. You work in steps.
Each step, reply with one JSON object and nothing else.
To call a tool: {"tool": "<name>", "argument": "<text>"}
To answer: {"final": "<text>"}
You may call tools over several steps before you answer.
Do not call a tool that already succeeded in this conversation.
Tools: echo, send_email, read_file, get_tool_schema.
Call get_tool_schema with a tool name before you use a tool whose arguments you do not know."""

V1_TOOLS = """get_tool_schema: {"tool": "get_tool_schema", "argument": "<tool name>"}
Answer: {"final": "<text>"}"""

V3_RULES = """You are an agent on a server. You work in steps.
Each step, reply with one JSON object and nothing else.
To call a tool: {"tool": "<name>", "argument": "<text>"}
To answer: {"final": "<text>"}
You may call tools over several steps before you answer.
Do not call a tool that already succeeded in this conversation.
Tools: echo, send_email, read_file, get_tool_schema, remember, note, recall, read_skill, delegate.
Use remember for facts that must survive. Use note for the current task.
Call get_tool_schema with a tool name before you use a tool you do not know.
Delegate work that needs many tool calls or reads a lot of data. The helper
returns a report; give it a self-contained task.
Skills: status-update. Read one with read_skill before using it."""
V3_TOOLS = """get_tool_schema: {"tool": "get_tool_schema", "argument": "<tool name>"}
Answer: {"final": "<text>"}"""

# Frozen. Do not edit: conversations pinned to this version must keep it.
V4_RULES = """You are an agent on a server. You work in steps.
Each step, reply with one JSON object and nothing else.
To call a tool: {"tool": "<name>", "argument": "<text>"}
To answer: {"final": "<text>"}
You may call tools over several steps before you answer.
Do not call a tool that already succeeded in this conversation.
Tools: echo, send_email, read_file, get_tool_schema, remember, note, recall, read_skill, delegate, collect, helpers, message_helper, stop_helper.
Use remember for facts that must survive. Use note for the current task.
Call get_tool_schema with a tool name before you use a tool you do not know.
Delegate starts a helper and returns its id; it does not wait. collect waits
for reports. helpers lists what is running. message_helper and stop_helper
manage one helper. Collect or stop every helper before you answer.
Delegate work that needs many tool calls or reads a lot of data. The helper
returns a report; give it a self-contained task.
Skills: status-update. Read one with read_skill before using it."""
V4_TOOLS = """get_tool_schema: {"tool": "get_tool_schema", "argument": "<tool name>"}
Answer: {"final": "<text>"}"""

# Frozen. Do not edit: conversations pinned to this version must keep it.
V5_RULES = """You are an agent on a server. You work in steps.
Each step, reply with one JSON object and nothing else.
To call a tool: {"tool": "<name>", "argument": "<text>"}
To answer: {"final": "<text>"}
You may call tools over several steps before you answer.
Do not call a tool that already succeeded in this conversation.
Tools: echo, send_email, read_file, get_tool_schema, remember, note, recall, read_skill, delegate, collect, helpers, message_helper, stop_helper.
Use remember for facts that must survive. Use note for the current task.
Call get_tool_schema with a tool name before you use a tool you do not know.
Delegate starts a helper and returns a task id; it does not wait. collect waits
for reports. helpers lists tasks and their status. message_helper and
stop_helper take a task id; stop_helper also takes all. Collect or stop every
task before you answer.
Delegate work that needs many tool calls or reads a lot of data. The helper
returns a report; give it a self-contained task.
Skills: status-update. Read one with read_skill before using it."""
V5_TOOLS = """get_tool_schema: {"tool": "get_tool_schema", "argument": "<tool name>"}
Answer: {"final": "<text>"}"""

RULES = """You are an agent on a server. You work in steps.
Each step, reply with one JSON object and nothing else.
To call a tool: {"tool": "<name>", "argument": "<text>"}
To answer: {"final": "<text>"}
You may call tools over several steps before you answer.
Do not call a tool that already succeeded in this conversation.
Tools: """ + TOOL_NAMES + """.
Use remember for facts that must survive. Use note for the current task.
Call get_tool_schema with a tool name before you use a tool you do not know.
Delegate starts a helper and returns a task id; it does not wait. collect waits
for a report. helpers lists tasks and their status. message_helper and
stop_helper take a task id; stop_helper also takes all. You may answer while
tasks run; a finished task reports to you as a new message.
Delegate work that needs many tool calls or reads a lot of data. The helper
returns a report; give it a self-contained task.
Skills: status-update. Read one with read_skill before using it."""
V3_TOOLS = """get_tool_schema: {"tool": "get_tool_schema", "argument": "<tool name>"}
Answer: {"final": "<text>"}"""

# Frozen. Do not edit: conversations pinned to this version must keep it.
V2_RULES = """You are an agent on a server. You work in steps.
Each step, reply with one JSON object and nothing else.
To call a tool: {"tool": "<name>", "argument": "<text>"}
To answer: {"final": "<text>"}
You may call tools over several steps before you answer.
Do not call a tool that already succeeded in this conversation.
Tools: echo, send_email, read_file, get_tool_schema, remember, note, recall, read_skill.
Use remember for facts that must survive. Use note for the current task.
Call get_tool_schema with a tool name before you use a tool you do not know.
Skills: status-update. Read one with read_skill before using it."""
V2_TOOLS = """get_tool_schema: {"tool": "get_tool_schema", "argument": "<tool name>"}
Answer: {"final": "<text>"}"""

TOOLS = """get_tool_schema: {"tool": "get_tool_schema", "argument": "<tool name>"}
Answer: {"final": "<text>"}"""

SYSTEM = RULES + "\n\n" + TOOLS

# A deploy adds a version and keeps the old ones, so running conversations
# keep the text they started with.
PROMPT_VERSION = "6"
PROMPTS = {
    "1": {
        "system": V1_RULES + "\n\n" + V1_TOOLS,
        "rules": _hash(V1_RULES),
        "tools": _hash(V1_TOOLS),
    },
    "2": {
        "system": V2_RULES + "\n\n" + V2_TOOLS,
        "rules": _hash(V2_RULES),
        "tools": _hash(V2_TOOLS),
    },
    "3": {
        "system": V3_RULES + "\n\n" + V3_TOOLS,
        "rules": _hash(V3_RULES),
        "tools": _hash(V3_TOOLS),
    },
    "4": {
        "system": V4_RULES + "\n\n" + V4_TOOLS,
        "rules": _hash(V4_RULES),
        "tools": _hash(V4_TOOLS),
    },
    "5": {
        "system": V5_RULES + "\n\n" + V5_TOOLS,
        "rules": _hash(V5_RULES),
        "tools": _hash(V5_TOOLS),
    },
    PROMPT_VERSION: {
        "system": SYSTEM,
        "rules": _hash(RULES),
        "tools": _hash(TOOLS),
    },
}

COMPACT_AFTER = 20
KEEP_TURNS = 6
ARTIFACTS = Path(".agent/artifacts")
SIZE_LIMIT = 2000
SKILLS = Path(__file__).resolve().parents[2] / "skills"

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


@dataclass
class History:
    """The conversation so far, plus a hash of its memory summary."""

    messages: list[dict]
    memory_hash: str


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
async def pin_prompt(org_id: str, conversation_id: str) -> str:
    """The prompt version this conversation started with.

    A deploy moves PROMPT_VERSION; a running conversation keeps its row.
    """
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        await conn.execute(
            "insert into conversations (org_id, conversation_id, prompt_version)"
            " values (%s, %s, %s) on conflict do nothing",
            (org_id, conversation_id, PROMPT_VERSION),
        )
        cursor = await conn.execute(
            "select prompt_version from conversations"
            " where org_id = %s and conversation_id = %s",
            (org_id, conversation_id),
        )
        version = (await cursor.fetchone())[0]
        if not version:
            await conn.execute(
                "update conversations set prompt_version = %s"
                " where org_id = %s and conversation_id = %s",
                (PROMPT_VERSION, org_id, conversation_id),
            )
            version = PROMPT_VERSION
        return version


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
    start = raw.find("{")
    if start == -1:
        return ModelReply(kind="final", text=text)
    try:
        # Models sometimes emit two actions in one reply; take the first.
        data, _ = json.JSONDecoder().raw_decode(raw[start:])
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
    org_id: str,
    conversation_id: str,
    seq: int,
    step: int,
    prompt_version: str,
    memory_hash: str,
    history: list[dict],
) -> ModelReply:
    """Ask the real model what to do next, and record what it cost.

    Sources: talk §04 (the model selects a tool call), talk §05 (a stable
    system prompt keeps the prefix cacheable), lesson 01.
    """
    prompt = PROMPTS.get(prompt_version)
    if prompt is None:
        raise ApplicationError(
            f"unknown prompt version: {prompt_version}", non_retryable=True
        )
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    body = _post(
        {
            "model": model,
            "messages": [{"role": "system", "content": prompt["system"]}, *history],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
    )
    usage = body.get("usage") or {}
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        await conn.execute(
            "insert into model_calls (org_id, conversation_id, seq, step, model,"
            " prompt_version, prompt_hash, hash_rules, hash_tools, hash_memory,"
            " prompt_tokens, cache_hit, cache_miss, completion_tokens)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " on conflict (org_id, conversation_id, seq, step) do update set"
            " model = excluded.model, prompt_version = excluded.prompt_version,"
            " prompt_hash = excluded.prompt_hash, hash_rules = excluded.hash_rules,"
            " hash_tools = excluded.hash_tools, hash_memory = excluded.hash_memory,"
            " prompt_tokens = excluded.prompt_tokens, cache_hit = excluded.cache_hit,"
            " cache_miss = excluded.cache_miss,"
            " completion_tokens = excluded.completion_tokens",
            (
                org_id,
                conversation_id,
                seq,
                step,
                model,
                prompt_version,
                _hash(prompt["system"]),
                prompt["rules"],
                prompt["tools"],
                memory_hash,
                usage.get("prompt_tokens", 0),
                usage.get("prompt_cache_hit_tokens", 0),
                usage.get("prompt_cache_miss_tokens", 0),
                usage.get("completion_tokens", 0),
            ),
        )
    return _parse_reply(body["choices"][0]["message"]["content"])


async def prewarm(org_id: str, conversation_id: str) -> None:
    """Warm the prefix when the client says the user is typing.

    Sources: talk §05 — pre-warm the cache like a prefetched link.
    """
    version = await pin_prompt(org_id, conversation_id)
    prompt = PROMPTS.get(version)
    if prompt is None:
        return
    _post(
        {
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": "warmup"},
            ],
            "temperature": 0,
            "max_tokens": 1,
        }
    )


@activity.defn
async def create_task(
    org_id: str, conversation_id: str, description: str, helper_workflow_id: str
) -> str:
    """Insert the to-do item and return its short id (t1, t2, ...)."""
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select count(*) from tasks where org_id = %s and conversation_id = %s",
            (org_id, conversation_id),
        )
        task_id = f"t{(await cursor.fetchone())[0] + 1}"
        await conn.execute(
            "insert into tasks (id, org_id, conversation_id, description, helper_workflow_id)"
            " values (%s, %s, %s, %s, %s)",
            (task_id, org_id, conversation_id, description, helper_workflow_id),
        )
        return task_id


@activity.defn
async def finish_task(
    org_id: str,
    conversation_id: str,
    task_id: str,
    status: str,
    report: str,
) -> None:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        await conn.execute(
            "update tasks set status = %s, report = %s, updated_at = now()"
            " where org_id = %s and conversation_id = %s and id = %s",
            (status, report, org_id, conversation_id, task_id),
        )


@activity.defn
async def list_tasks(org_id: str, conversation_id: str) -> str:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select id, status, description from tasks"
            " where org_id = %s and conversation_id = %s order by created_at",
            (org_id, conversation_id),
        )
        rows = [f"{task_id} {status}: {description}" async for task_id, status, description in cursor]
        return "\n".join(rows) or "no tasks"


async def _report(
    conn: psycopg.AsyncConnection,
    org_id: str,
    conversation_id: str,
    task_id: str,
    status: str,
    report: str,
) -> None:
    """Write the task result and queue the completion event, atomically."""
    envelope = Envelope(
        event_id=f"helper:{org_id}:{conversation_id}:{task_id}:{status}",
        type=HELPER_COMPLETED,
        org_id=org_id,
        subject={"conversation_id": conversation_id, "task_id": task_id},
        payload={"report": report, "status": status},
        occurred_at=datetime.now(timezone.utc).isoformat(),
    )
    await conn.execute(
        "update tasks set status = %s, report = %s, updated_at = now()"
        " where org_id = %s and conversation_id = %s and id = %s",
        (status, report, org_id, conversation_id, task_id),
    )
    await conn.execute(
        "insert into outbox (id, topic, payload) values (%s, %s, %s)"
        " on conflict do nothing",
        (envelope.event_id, HELPERS_TOPIC, envelope.to_json().decode()),
    )


@activity.defn
async def report_task(
    org_id: str, conversation_id: str, task_id: str, status: str, report: str
) -> None:
    """The helper's own report. One transaction: row and event together."""
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.transaction():
            await _report(conn, org_id, conversation_id, task_id, status, report)


async def reap_tasks() -> int:
    """Fail tasks whose helper never reported. The projection needs a reconciler.

    The 35-minute mark sits just past the child's 30-minute execution timeout.
    """
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.transaction():
            cursor = await conn.execute(
                "select org_id, conversation_id, id from tasks"
                " where status = 'running'"
                " and updated_at < now() - interval '35 minutes'"
            )
            rows = await cursor.fetchall()
            for org_id, conversation_id, task_id in rows:
                await _report(
                    conn,
                    org_id,
                    conversation_id,
                    task_id,
                    "failed",
                    "helper did not report within its time limit",
                )
            return len(rows)


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
async def load_history(org_id: str, conversation_id: str) -> History:
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
        message_rows = await cursor.fetchall()
        cursor = await conn.execute(
            "select kind, content from memories"
            " where org_id = %s and conversation_id = %s"
            " and (kind = 'fact' or created_at > now() - interval '1 hour')"
            " order by created_at",
            (org_id, conversation_id),
        )
        rows = await cursor.fetchall()
        facts = [content for kind, content in rows if kind == "fact"]
        scratch = [content for kind, content in rows if kind == "scratch"]

        history: list[dict] = []
        if facts:
            history.append(
                {
                    "role": "assistant",
                    "content": "Known facts:\n" + "\n".join(f"- {fact}" for fact in facts),
                }
            )
        if summary:
            history.append({"role": "assistant", "content": f"Earlier work: {summary}"})
        for role, content in message_rows:
            if role == "tool":
                history.append({"role": "user", "content": f"tool result: {content}"})
            else:
                history.append({"role": role, "content": content})
        if scratch:
            history.append(
                {
                    "role": "user",
                    "content": "Scratchpad:\n" + "\n".join(f"- {item}" for item in scratch),
                }
            )
        return History(
            messages=history,
            memory_hash=_hash(summary + "\n" + "\n".join(facts)),
        )


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


async def _write_memory(
    org_id: str, conversation_id: str, kind: str, content: str, effect_token: str
) -> None:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.transaction():
            if not await _claim(conn, effect_token, kind, content):
                return
            await conn.execute(
                "insert into memories (org_id, conversation_id, kind, content)"
                " values (%s, %s, %s, %s)",
                (org_id, conversation_id, kind, content),
            )


async def _recall(org_id: str, conversation_id: str, query: str) -> str:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select content, created_at from memories"
            " where org_id = %s and conversation_id = %s and content ilike %s"
            " order by created_at desc limit 5",
            (org_id, conversation_id, f"%{query}%"),
        )
        lines = [f"{created:%Y-%m-%d} memory: {content}" async for content, created in cursor]
        cursor = await conn.execute(
            "select content, created_at from messages"
            " where org_id = %s and conversation_id = %s and content ilike %s"
            " order by seq desc limit 5",
            (org_id, conversation_id, f"%{query}%"),
        )
        lines += [f"{created:%Y-%m-%d} message: {content}" async for content, created in cursor]
    return "\n".join(lines) or f"nothing found for: {query}"


async def _effect(tool: str, argument: str, effect_token: str) -> ToolResult:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        await _claim(conn, effect_token, tool, argument)

    if len(argument) > SIZE_LIMIT:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        stored = hashlib.sha256(effect_token.encode()).hexdigest()[:16] + ".txt"
        (ARTIFACTS / stored).write_text(argument)
        output = argument[:500] + f"... [stored: {stored}] ({len(argument)} chars)"
    else:
        output = argument
    return ToolResult(ok=True, output=output)


async def _echo(org_id, conversation_id, argument, effect_token) -> ToolResult:
    return await _effect("echo", argument, effect_token)


async def _send_email(org_id, conversation_id, argument, effect_token) -> ToolResult:
    return await _effect("send_email", argument, effect_token)


async def _read_file(org_id, conversation_id, argument, effect_token) -> ToolResult:
    path = ARTIFACTS / Path(argument).name
    if not path.is_file():
        return ToolResult(ok=False, output=f"no such file: {argument}")
    return ToolResult(ok=True, output=path.read_text()[:4000])


async def _read_skill(org_id, conversation_id, argument, effect_token) -> ToolResult:
    path = SKILLS / Path(argument).stem / "SKILL.md"
    if not path.is_file():
        return ToolResult(ok=False, output=f"no such skill: {argument}")
    return ToolResult(ok=True, output=path.read_text()[:4000])


async def _get_tool_schema(org_id, conversation_id, argument, effect_token) -> ToolResult:
    schema = TOOL_SCHEMAS.get(argument)
    return ToolResult(ok=bool(schema), output=schema or f"unknown tool: {argument}")


async def _recall_tool(org_id, conversation_id, argument, effect_token) -> ToolResult:
    return ToolResult(ok=True, output=await _recall(org_id, conversation_id, argument))


async def _remember(org_id, conversation_id, argument, effect_token) -> ToolResult:
    await _write_memory(org_id, conversation_id, "fact", argument, effect_token)
    return ToolResult(ok=True, output="fact stored")


async def _note(org_id, conversation_id, argument, effect_token) -> ToolResult:
    await _write_memory(org_id, conversation_id, "scratch", argument, effect_token)
    return ToolResult(ok=True, output="scratch stored")


# One handler per name. The test checks this table against TOOL_SPECS.
ACTIVITY_TOOLS = {
    "echo": _echo,
    "send_email": _send_email,
    "read_file": _read_file,
    "read_skill": _read_skill,
    "get_tool_schema": _get_tool_schema,
    "recall": _recall_tool,
    "remember": _remember,
    "note": _note,
}


@activity.defn
async def run_tool(
    org_id: str,
    conversation_id: str,
    name: str,
    argument: str,
    effect_token: str,
) -> ToolResult:
    """Execute one tool call, at most once per token.

    Sources: talk §04 (the harness, not the model, executes tools); talk §05
    (long output to a file); lesson 07 (memory layers); EDA §5 (effect tokens).
    """
    handler = ACTIVITY_TOOLS.get(name)
    if handler is None:
        return ToolResult(ok=False, output=f"unknown tool: {name}")
    return await handler(org_id, conversation_id, argument, effect_token)
