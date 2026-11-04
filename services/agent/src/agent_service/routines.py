"""Routines: a Temporal Schedule that starts a turn.

Sources
    EDA §4.3 — UpdateRoutine creates or changes a Temporal Schedule
    talk §03 — a routine is a trigger that wakes the agent

Delta
    CLI-only for now; the bus command waits for authenticated commands.
    The schedule starts RunWorkflow with kind="routine".
"""

from __future__ import annotations

import os
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
    ScheduleUpdate,
)
from temporalio.service import RPCError, RPCStatusCode

from agent_service.activities import _dsn
from agent_service.worker import TASK_QUEUE
from agent_service.workflow import RunRequest, RunWorkflow


async def _connect() -> Client:
    return await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"))


def _schedule(row: dict) -> Schedule:
    action = ScheduleActionStartWorkflow(
        RunWorkflow.run,
        RunRequest(
            conversation_id=row["conversation_id"],
            text=row["text"],
            org_id=row["org_id"],
            kind="routine",
            routine_id=row["id"],
        ),
        id=f"routine:{row['id']}",
        task_queue=TASK_QUEUE,
    )
    spec = ScheduleSpec(
        cron_expressions=[row["cron"]], time_zone_name=row["timezone"]
    )
    policy = SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP)
    return Schedule(action=action, spec=spec, policy=policy)


async def _upsert_schedule(client: Client, row: dict) -> None:
    schedule_id = f"routine:{row['id']}"
    try:
        await client.create_schedule(schedule_id, _schedule(row))
    except ScheduleAlreadyRunningError:
        handle = client.get_schedule_handle(schedule_id)
        await handle.update(lambda _: ScheduleUpdate(schedule=_schedule(row)))


async def create_routine(
    org_id: str,
    conversation_id: str,
    cron: str,
    text: str,
    timezone: str = "UTC",
    client: Client | None = None,
) -> str:
    """Insert the routine, then create its Schedule. Rolls back the row on failure."""
    try:
        ZoneInfo(timezone)
    except Exception as exc:
        raise ValueError(f"unknown timezone: {timezone}") from exc
    if not cron.strip():
        raise ValueError("cron must not be empty")
    routine_id = f"rt_{uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        await conn.execute(
            "insert into routines"
            " (id, org_id, conversation_id, cron, timezone, text)"
            " values (%s, %s, %s, %s, %s, %s)",
            (routine_id, org_id, conversation_id, cron, timezone, text),
        )
    try:
        await _upsert_schedule(client or await _connect(), await get_routine(routine_id))
    except Exception:
        async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
            await conn.execute("delete from routines where id = %s", (routine_id,))
        raise
    return routine_id


async def get_routine(routine_id: str) -> dict | None:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select id, org_id, conversation_id, cron, timezone, text, enabled"
            " from routines where id = %s",
            (routine_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    keys = ("id", "org_id", "conversation_id", "cron", "timezone", "text", "enabled")
    return dict(zip(keys, row))


async def list_routines(org_id: str, conversation_id: str | None = None) -> list[dict]:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        if conversation_id is None:
            cursor = await conn.execute(
                "select id, org_id, conversation_id, cron, timezone, text, enabled"
                " from routines where org_id = %s order by created_at",
                (org_id,),
            )
        else:
            cursor = await conn.execute(
                "select id, org_id, conversation_id, cron, timezone, text, enabled"
                " from routines where org_id = %s and conversation_id = %s"
                " order by created_at",
                (org_id, conversation_id),
            )
        rows = await cursor.fetchall()
    keys = ("id", "org_id", "conversation_id", "cron", "timezone", "text", "enabled")
    return [dict(zip(keys, row)) for row in rows]


async def set_enabled(
    routine_id: str, enabled: bool, client: Client | None = None
) -> None:
    if await get_routine(routine_id) is None:
        raise ValueError(f"no such routine: {routine_id}")
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        await conn.execute(
            "update routines set enabled = %s, updated_at = now() where id = %s",
            (enabled, routine_id),
        )
    handle = (client or await _connect()).get_schedule_handle(f"routine:{routine_id}")
    if enabled:
        await handle.unpause()
    else:
        await handle.pause()


async def delete_routine(routine_id: str, client: Client | None = None) -> None:
    if await get_routine(routine_id) is None:
        raise ValueError(f"no such routine: {routine_id}")
    handle = (client or await _connect()).get_schedule_handle(f"routine:{routine_id}")
    try:
        await handle.delete()
    except RPCError as exc:
        if exc.status != RPCStatusCode.NOT_FOUND:
            raise
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        await conn.execute("delete from routines where id = %s", (routine_id,))


async def delete_schedules_for(
    org_id: str, conversation_id: str | None = None, client: Client | None = None
) -> None:
    """Delete the Schedules for a scope before its rows are deleted."""
    rows = await list_routines(org_id, conversation_id)
    client = client or await _connect()
    for row in rows:
        handle = client.get_schedule_handle(f"routine:{row['id']}")
        try:
            await handle.delete()
        except RPCError as exc:
            if exc.status != RPCStatusCode.NOT_FOUND:
                raise
