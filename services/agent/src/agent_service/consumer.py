"""The consumer: a bus event starts a turn.

Sources
    talk §03 — the agent wakes on an event it did not ask for
    EDA §5 — dedupe before the workflow, so redelivery is a no-op
    EDA §4.3 — `SendMessage` is the only write path from outside

Delta
    The CLI was the only trigger. Now a Kafka topic is, and the inbox table
    makes at-least-once delivery harmless.
"""

from __future__ import annotations

import asyncio
import os

import psycopg
from aiokafka import AIOKafkaConsumer
from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDConflictPolicy

from agent_service.activities import _dsn, next_seq
from agent_service.events import SEND_MESSAGE, Envelope
from agent_service.worker import TASK_QUEUE
from agent_service.workflow import RunRequest, RunWorkflow

TOPIC = "agent.commands"


async def _claim(envelope: Envelope) -> bool:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "insert into inbox (event_id, org_id) values (%s, %s)"
            " on conflict do nothing returning event_id",
            (envelope.event_id, envelope.org_id),
        )
        return await cursor.fetchone() is not None


async def handle(client: Client, envelope: Envelope) -> WorkflowHandle | None:
    """Start one turn from one event. None if the event was already handled."""
    if envelope.type != SEND_MESSAGE:
        raise ValueError(f"unsupported event type: {envelope.type}")
    conversation_id = envelope.subject["conversation_id"]
    text = envelope.payload["text"]

    if not await _claim(envelope):
        return None

    seq = await next_seq(envelope.org_id, conversation_id)
    return await client.start_workflow(
        RunWorkflow.run,
        RunRequest(
            conversation_id=conversation_id,
            text=text,
            seq=seq,
            org_id=envelope.org_id,
        ),
        id=f"run:{conversation_id}:{seq}",
        task_queue=TASK_QUEUE,
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
    )


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
