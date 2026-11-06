"""Retention and deletion for the agent database.

Sources
    BUILD §3 — migrations, health, runbooks
    BUILD §6.2 — the agent service owns conversations and message state
    BUILD §11 — the event retention window was open
    EDA §9 — retention limits for logs
    EDA §12 — a terminal failure must be recorded, not lost

Delta
    Concrete windows, a hard delete with an audit row, and an hourly purge.
"""

from __future__ import annotations

import asyncio
import json

import psycopg

from agent_service import storage
from agent_service.activities import _dsn

MESSAGE_DAYS = 60
MODEL_CALL_DAYS = 60
EFFECT_DAYS = 180
INBOX_DAYS = 180
OUTBOX_DAYS = 180
APPROVAL_DAYS = 730
REVIEW_DAYS = 730
TASK_DAYS = 180
NOTIFICATION_DAYS = 180
DELETION_DAYS = 730
ARTIFACT_DAYS = storage.ARTIFACT_DAYS

RETENTION = [
    ("messages", "created_at", MESSAGE_DAYS),
    ("model_calls", "created_at", MODEL_CALL_DAYS),
    ("effects", "created_at", EFFECT_DAYS),
    ("inbox", "received_at", INBOX_DAYS),
    ("outbox", "created_at", OUTBOX_DAYS),
    ("approvals", "created_at", APPROVAL_DAYS),
    ("reviews", "created_at", REVIEW_DAYS),
    ("tasks", "created_at", TASK_DAYS),
    ("notifications", "last_at", NOTIFICATION_DAYS),
    ("deletions", "deleted_at", DELETION_DAYS),
]

SCOPED = [
    "messages",
    "model_calls",
    "memories",
    "tasks",
    "approvals",
    "reviews",
    "notifications",
    "conversation_locks",
    "conversations",
    "effects",
    "outbox",
    "routines",
    "artifacts",
]


async def purge() -> dict[str, int]:
    """Delete rows older than their window. Returns the non-zero counts."""
    counts: dict[str, int] = {}
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.transaction():
            for table, column, days in RETENTION:
                cursor = await conn.execute(
                    f"delete from {table}"
                    f" where {column} < now() - (%s * interval '1 day')",
                    (days,),
                )
                if cursor.rowcount:
                    counts[table] = cursor.rowcount
            cursor = await conn.execute(
                "delete from conversation_locks where expires_at < now()"
            )
            if cursor.rowcount:
                counts["conversation_locks"] = cursor.rowcount
    purged_artifacts = await asyncio.to_thread(storage.purge, ARTIFACT_DAYS)
    if purged_artifacts:
        counts["artifacts"] = purged_artifacts
    return counts


async def delete_scope(org_id: str, conversation_id: str | None = None) -> dict[str, int]:
    """Hard-delete one conversation, or the whole org when conversation is None.

    A live conversation lock blocks the delete: a running turn could write again.
    """
    counts: dict[str, int] = {}
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.transaction():
            if conversation_id is None:
                cursor = await conn.execute(
                    "select count(*) from conversation_locks"
                    " where org_id = %s and expires_at > now()",
                    (org_id,),
                )
            else:
                cursor = await conn.execute(
                    "select count(*) from conversation_locks"
                    " where org_id = %s and conversation_id = %s and expires_at > now()",
                    (org_id, conversation_id),
                )
            if (await cursor.fetchone())[0]:
                raise RuntimeError("conversation is busy; stop the turn first")

            await asyncio.to_thread(storage.delete_objects, org_id, conversation_id)

            for table in SCOPED:
                if conversation_id is None:
                    cursor = await conn.execute(
                        f"delete from {table} where org_id = %s", (org_id,)
                    )
                else:
                    cursor = await conn.execute(
                        f"delete from {table}"
                        " where org_id = %s and conversation_id = %s",
                        (org_id, conversation_id),
                    )
                if cursor.rowcount:
                    counts[table] = cursor.rowcount
            if conversation_id is None:
                cursor = await conn.execute(
                    "delete from inbox where org_id = %s", (org_id,)
                )
                if cursor.rowcount:
                    counts["inbox"] = cursor.rowcount

            await conn.execute(
                "insert into deletions (org_id, conversation_id, counts)"
                " values (%s, %s, %s::jsonb)",
                (org_id, conversation_id or "", json.dumps(counts)),
            )
    return counts
