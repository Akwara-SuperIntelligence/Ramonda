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
import json
import os

import psycopg
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from agent_service.activities import (
    _argument_from_fields,
    _dsn,
    _resolved_envelope,
    prewarm,
    reap_tasks,
    wrap_untrusted,
)
from agent_service.events import (
    APPROVAL_TOPIC,
    HELPER_COMPLETED,
    HELPERS_TOPIC,
    RESOLVE_APPROVAL,
    SEND_MESSAGE,
    TYPING,
    Envelope,
)
from agent_service.health import start_health_server
from agent_service.maintenance import purge
from agent_service.worker import TASK_QUEUE
from agent_service.workflow import RunRequest, RunWorkflow

TOPIC = "agent.commands"
DLQ_TOPIC = "agent.commands.dlq"
DECISIONS = ("approved", "denied")

# Per-org active-run caps by priority. Interactive is never dropped.
# routine/backfill are skipped (offset still commits) when the org is over cap,
# until preemption and batching exist. See ADR 0004.
MAX_ACTIVE_RUNS = {"interactive": 2, "routine": 1, "backfill": 1}


async def _active_runs(org_id: str) -> int:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select count(*) from conversation_locks"
            " where org_id = %s and expires_at > now()",
            (org_id,),
        )
        return (await cursor.fetchone())[0]


async def _over_quota(envelope: Envelope) -> bool:
    """True when starting this turn would exceed the org's active-run cap."""
    if envelope.priority == "interactive":
        return False
    cap = MAX_ACTIVE_RUNS.get(envelope.priority, MAX_ACTIVE_RUNS["routine"])
    active = await _active_runs(envelope.org_id)
    return active >= cap


async def _claim(envelope: Envelope) -> bool:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "insert into inbox (event_id, org_id) values (%s, %s)"
            " on conflict do nothing returning event_id",
            (envelope.event_id, envelope.org_id),
        )
        return await cursor.fetchone() is not None


async def _start(
    client: Client,
    envelope: Envelope,
    text: str,
    kind: str = "user",
    failed: bool = False,
) -> WorkflowHandle:
    """Start the turn. The workflow ID makes a repeat safe."""
    workflow_id = f"turn:{envelope.event_id}"
    try:
        return await client.start_workflow(
            RunWorkflow.run,
            RunRequest(
                conversation_id=envelope.subject["conversation_id"],
                text=text,
                org_id=envelope.org_id,
                kind=kind,
                failed=failed,
                traceparent=envelope.traceparent,
                approval_timeout_minutes=int(
                    os.environ.get("APPROVAL_TIMEOUT_MINUTES", "1440")
                ),
            ),
            id=workflow_id,
            task_queue=TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
    except WorkflowAlreadyStartedError:
        return client.get_workflow_handle(workflow_id)


async def _stop_active(client: Client, envelope: Envelope) -> None:
    """A new user message preempts a long run in the same conversation."""
    conversation_id = envelope.subject["conversation_id"]
    workflow_id = f"turn:{envelope.event_id}"
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select workflow_id from conversation_locks"
            " where org_id = %s and conversation_id = %s and workflow_id <> %s",
            (envelope.org_id, conversation_id, workflow_id),
        )
        row = await cursor.fetchone()
    if row is None:
        return
    try:
        await client.get_workflow_handle(row[0]).signal(
            "stop", "superseded by a new user message"
        )
    except Exception:
        # The run may have finished between the query and the signal.
        return


async def _resolve(client: Client, envelope: Envelope) -> WorkflowHandle | None:
    """Record the decision once, then signal. A repeat signal is harmless."""
    approval_id = envelope.payload["approval_id"]
    decision = envelope.payload["decision"]
    argument = envelope.payload.get("argument")
    fields = envelope.payload.get("fields")
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision: {decision}")
    if argument is not None and not isinstance(argument, str):
        raise ValueError("argument must be a string")
    if fields is not None and not isinstance(fields, list):
        raise ValueError("fields must be a list")
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.transaction():
            if fields is not None:
                cursor = await conn.execute(
                    "select action from approvals where id = %s", (approval_id,)
                )
                base = await cursor.fetchone()
                if base is None:
                    return None
                argument = _argument_from_fields(base[0], fields)
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
                    "insert into outbox"
                    " (id, topic, payload, org_id, conversation_id)"
                    " values (%s, %s, %s, %s, %s) on conflict do nothing",
                    (
                        f"approval-resolved:{approval_id}:{decision}",
                        APPROVAL_TOPIC,
                        event.to_json().decode(),
                        org_id,
                        conversation_id,
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
        report = envelope.payload["report"]
        text = f"helper {task_id} finished: {wrap_untrusted(report)}"
        handle = await _start(
            client,
            envelope,
            text,
            kind="helper",
            failed=envelope.payload.get("status") == "failed",
        )
    else:
        if await _over_quota(envelope):
            return None
        await _stop_active(client, envelope)
        handle = await _start(client, envelope, envelope.payload["text"])
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


async def _maintenance_loop() -> None:
    while True:
        try:
            counts = await purge()
            if counts:
                print(f"[purged] {counts}", flush=True)
        except Exception as exc:
            print(f"[purge failed] {exc}", flush=True)
        await asyncio.sleep(3600)


async def _dead_letter(producer: AIOKafkaProducer, message, exc: Exception) -> None:
    try:
        event = json.loads(message.value)
    except Exception:
        event = {"raw": message.value.decode(errors="replace")}
    payload = json.dumps(
        {"error": f"{type(exc).__name__}: {exc}", "event": event}
    ).encode()
    await producer.send_and_wait(DLQ_TOPIC, payload)


async def main() -> None:
    start_health_server(int(os.environ.get("HEALTH_PORT", "8081")), "consumer")
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
    producer = AIOKafkaProducer(
        bootstrap_servers=os.environ.get("KAFKA_BROKERS", "localhost:9092")
    )
    await consumer.start()
    await producer.start()
    reaper = asyncio.create_task(_reap_loop())
    maintenance = asyncio.create_task(_maintenance_loop())
    print(f"consumer ready: {TOPIC}", flush=True)
    try:
        async for message in consumer:
            try:
                await handle(client, Envelope.from_json(message.value))
            except (ValueError, KeyError) as exc:
                await _dead_letter(producer, message, exc)
                print(f"[dlq] {exc}", flush=True)
            # An unhandled error stops the consumer before this line. The
            # offset stays uncommitted and the bus redelivers the command.
            await consumer.commit()
    finally:
        reaper.cancel()
        maintenance.cancel()
        await consumer.stop()
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
