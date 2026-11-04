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
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from agent_service.activities import _dsn, _resolved_envelope, prewarm, reap_tasks
from agent_service.events import (
    APPROVAL_TOPIC,
    HELPER_COMPLETED,
    HELPERS_TOPIC,
    RESOLVE_APPROVAL,
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
    """Start the turn. The workflow ID makes a repeat safe."""
    workflow_id = f"turn:{envelope.event_id}"
    try:
        return await client.start_workflow(
            RunWorkflow.run,
            RunRequest(
                conversation_id=envelope.subject["conversation_id"],
                text=text,
                org_id=envelope.org_id,
            ),
            id=workflow_id,
            task_queue=TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
    except WorkflowAlreadyStartedError:
        return client.get_workflow_handle(workflow_id)


async def _resolve(client: Client, envelope: Envelope) -> WorkflowHandle | None:
    """Record the decision once, then signal. A repeat signal is harmless."""
    approval_id = envelope.payload["approval_id"]
    decision = envelope.payload["decision"]
    argument = envelope.payload.get("argument")
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision: {decision}")
    if argument is not None and not isinstance(argument, str):
        raise ValueError("argument must be a string")
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.transaction():
            cursor = await conn.execute(
                "update approvals set status = %s, resolved_at = now(),"
                " arguments = coalesce(%s, arguments)"
                " where id = %s and status = 'pending'"
                " returning workflow_id, conversation_id, org_id, arguments",
                (decision, argument, approval_id),
            )
            row = await cursor.fetchone()
            if row is None:
                # A different decision already won; this one is ignored.
                cursor = await conn.execute(
                    "select workflow_id, arguments from approvals"
                    " where id = %s and status = %s",
                    (approval_id, decision),
                )
                row = await cursor.fetchone()
                if row is None:
                    return None
                workflow_id, argument = row
            else:
                workflow_id, conversation_id, org_id, argument = row
                event = _resolved_envelope(
                    approval_id, decision, org_id, conversation_id, argument
                )
                await conn.execute(
                    "insert into outbox (id, topic, payload) values (%s, %s, %s)"
                    " on conflict do nothing",
                    (
                        f"approval-resolved:{approval_id}:{decision}",
                        APPROVAL_TOPIC,
                        event.to_json().decode(),
                    ),
                )
    handle = client.get_workflow_handle(workflow_id)
    try:
        await handle.signal("resolve", args=[decision, approval_id, argument])
    except RPCError as exc:
        # The turn is already finished; the decision is still recorded.
        if exc.status != RPCStatusCode.NOT_FOUND:
            raise
    return handle if await _claim(envelope) else None


async def handle(client: Client, envelope: Envelope) -> WorkflowHandle | None:
    """Handle one command. None if it was already handled or had no effect."""
    if envelope.type not in (SEND_MESSAGE, RESOLVE_APPROVAL, TYPING, HELPER_COMPLETED):
        raise ValueError(f"unsupported event type: {envelope.type}")
    if envelope.type == TYPING:
        if not await _claim(envelope):
            return None
        await prewarm(envelope.org_id, envelope.subject["conversation_id"])
        return None
    if envelope.type == RESOLVE_APPROVAL:
        return await _resolve(client, envelope)
    if envelope.type == HELPER_COMPLETED:
        task_id = envelope.subject["task_id"]
        text = f"helper {task_id} finished: {envelope.payload['report']}"
    else:
        text = envelope.payload["text"]
    handle = await _start(client, envelope, text)
    # The inbox is written after the effect. A crash here repeats the start,
    # which the workflow ID absorbs; it does not lose the command.
    if not await _claim(envelope):
        return None
    return handle


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
            except (ValueError, KeyError) as exc:
                # Poison command: record it and move on.
                print(f"[skip] {exc}", flush=True)
            # An unhandled error stops the consumer before this line. The
            # offset stays uncommitted and the bus redelivers the command.
            await consumer.commit()
    finally:
        reaper.cancel()
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())
