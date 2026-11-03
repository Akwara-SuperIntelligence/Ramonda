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
from temporalio.common import WorkflowIDConflictPolicy

from agent_service.activities import _dsn, next_seq
from agent_service.events import APPROVAL_RESOLVED, SEND_MESSAGE, Envelope
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


async def _start(client: Client, envelope: Envelope) -> WorkflowHandle:
    conversation_id = envelope.subject["conversation_id"]
    # Serialise the read of the next turn number with the start, per conversation.
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.transaction():
            await conn.execute(
                "select pg_advisory_xact_lock(hashtext(%s))",
                (f"{envelope.org_id}:{conversation_id}",),
            )
            seq = await next_seq(conn, envelope.org_id, conversation_id)
            return await client.start_workflow(
                RunWorkflow.run,
                RunRequest(
                    conversation_id=conversation_id,
                    text=envelope.payload["text"],
                    seq=seq,
                    org_id=envelope.org_id,
                ),
                id=f"run:{conversation_id}:{seq}",
                task_queue=TASK_QUEUE,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
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
    if envelope.type not in (SEND_MESSAGE, APPROVAL_RESOLVED):
        raise ValueError(f"unsupported event type: {envelope.type}")
    if not await _claim(envelope):
        return None
    if envelope.type == APPROVAL_RESOLVED:
        return await _resolve(client, envelope)
    return await _start(client, envelope)


async def main() -> None:
    client = await Client.connect(
        os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    )
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=os.environ.get("KAFKA_BROKERS", "localhost:9092"),
        group_id="agent-service",
        auto_offset_reset="earliest",
    )
    await consumer.start()
    print(f"consumer ready: {TOPIC}", flush=True)
    try:
        async for message in consumer:
            try:
                await handle(client, Envelope.from_json(message.value))
            except Exception as exc:
                print(f"[skip] {exc}", flush=True)
            await consumer.commit()
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())
