"""The consumer: bus events start turns and resolve approvals.

Sources
    talk §03 — the agent wakes on an event it did not ask for
    talk §04 — draft, ask, then act
    EDA §4.3 — commands are the only write path from outside
    EDA §5 — dedupe before the workflow, so redelivery is a no-op

Delta
    A second command type. An approval resolution flips the row at most once
    and signals the waiting workflow.
"""

from __future__ import annotations

import asyncio
import os

import psycopg
from aiokafka import AIOKafkaConsumer
from temporalio.client import Client, WorkflowHandle

from agent_service.activities import _dsn, prewarm, reap_tasks
from agent_service.events import (
    APPROVAL_RESOLVED,
    HELPER_COMPLETED,
    HELPERS_TOPIC,
    SEND_MESSAGE,
    TYPING,
    Envelope,
)
from agent_service.worker import TASK_QUEUE
from agent_service.workflow import RunRequest, RunWorkflow

TOPIC = "agent.commands"
DECISIONS = ("approved", "denied")


async def _claim(envelope: Envelope) -> bool:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "insert into inbox (event_id, org_id) values (%s, %s)"
            " on conflict do nothing returning event_id",
            (envelope.event_id, envelope.org_id),
        )
        return await cursor.fetchone() is not None


async def _start(client: Client, envelope: Envelope, text: str) -> WorkflowHandle:
    return await client.start_workflow(
        RunWorkflow.run,
        RunRequest(
            conversation_id=envelope.subject["conversation_id"],
            text=text,
            org_id=envelope.org_id,
        ),
        id=f"turn:{envelope.event_id}",
        task_queue=TASK_QUEUE,
    )


async def _resolve(client: Client, envelope: Envelope) -> WorkflowHandle | None:
    approval_id = envelope.payload["approval_id"]
    decision = envelope.payload["decision"]
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision: {decision}")
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "update approvals set status = %s, resolved_at = now()"
            " where id = %s and status = 'pending' returning workflow_id",
            (decision, approval_id),
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    handle = client.get_workflow_handle(row[0])
    await handle.signal("resolve", args=[decision, approval_id])
    return handle


async def handle(client: Client, envelope: Envelope) -> WorkflowHandle | None:
    """Handle one command. None if it was already handled or had no effect."""
    if envelope.type not in (SEND_MESSAGE, APPROVAL_RESOLVED, TYPING, HELPER_COMPLETED):
        raise ValueError(f"unsupported event type: {envelope.type}")
    if not await _claim(envelope):
        return None
    if envelope.type == TYPING:
        await prewarm(envelope.org_id, envelope.subject["conversation_id"])
        return None
    if envelope.type == APPROVAL_RESOLVED:
        return await _resolve(client, envelope)
    if envelope.type == HELPER_COMPLETED:
        task_id = envelope.subject["task_id"]
        text = f"helper {task_id} finished: {envelope.payload['report']}"
        return await _start(client, envelope, text)
    return await _start(client, envelope, envelope.payload["text"])


async def _reap_loop() -> None:
    while True:
        try:
            reaped = await reap_tasks()
            if reaped:
                print(f"[reaped] {reaped} stale task(s)", flush=True)
        except Exception as exc:
            print(f"[reap failed] {exc}", flush=True)
        await asyncio.sleep(60)


async def main() -> None:
    client = await Client.connect(
        os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    )
    consumer = AIOKafkaConsumer(
        TOPIC,
        HELPERS_TOPIC,
        bootstrap_servers=os.environ.get("KAFKA_BROKERS", "localhost:9092"),
        group_id="agent-service",
        auto_offset_reset="earliest",
    )
    await consumer.start()
    reaper = asyncio.create_task(_reap_loop())
    print(f"consumer ready: {TOPIC}", flush=True)
    try:
        async for message in consumer:
            try:
                await handle(client, Envelope.from_json(message.value))
            except Exception as exc:
                print(f"[skip] {exc}", flush=True)
            await consumer.commit()
    finally:
        reaper.cancel()
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())
