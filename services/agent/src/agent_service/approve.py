"""Approve or deny one request, from the terminal.

Sources
    talk §04 — the human answers the draft; lesson 09.

Delta
    This is the approval card, with no card. It publishes the same command a
    Slack button will publish later.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from uuid import uuid4

import psycopg
from aiokafka import AIOKafkaProducer

from agent_service.activities import _dsn
from agent_service.consumer import TOPIC
from agent_service.events import RESOLVE_APPROVAL, Envelope


async def main(approval_id: str, decision: str, argument: str | None = None) -> None:
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        cursor = await conn.execute(
            "select org_id from approvals where id = %s", (approval_id,)
        )
        row = await cursor.fetchone()
    if row is None:
        raise SystemExit(f"no such approval: {approval_id}")

    payload = {"approval_id": approval_id, "decision": decision}
    if argument is not None:
        payload["argument"] = argument
    envelope = Envelope(
        event_id=f"resolve:{approval_id}:{uuid4().hex}",
        type=RESOLVE_APPROVAL,
        org_id=row[0],
        subject={"approval_id": approval_id},
        payload=payload,
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=os.environ.get("KAFKA_BROKERS", "localhost:9092")
    )
    await producer.start()
    try:
        await producer.send_and_wait(TOPIC, envelope.to_json())
    finally:
        await producer.stop()
    edit = f" (edited: {argument})" if argument is not None else ""
    print(f"{decision}: {approval_id}{edit}")


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="resolve an approval")
    parser.add_argument("approval_id")
    parser.add_argument("decision", choices=["approved", "denied"])
    parser.add_argument("--argument", help="edited arguments to approve")
    args = parser.parse_args()
    asyncio.run(main(args.approval_id, args.decision, args.argument))


if __name__ == "__main__":
    main_cli()
