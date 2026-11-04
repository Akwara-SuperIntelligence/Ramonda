"""Delivery: the thinnest possible client.

Sources
    talk §04 — the client receives one boundary and renders it
    lesson 09 — an approval is a card, not a sentence
    EDA §4.2 — message and approval events

Delta
    Prints messages and approval requests. A Slack or web client replaces this
    file and nothing else changes.
"""

from __future__ import annotations

import asyncio
import os

from aiokafka import AIOKafkaConsumer

from agent_service.events import (
    APPROVAL_REQUESTED,
    APPROVAL_RESOLVED,
    APPROVAL_TOPIC,
    MESSAGE_COMPOSED,
    MESSAGE_TOPIC,
    Envelope,
)


async def main() -> None:
    consumer = AIOKafkaConsumer(
        MESSAGE_TOPIC,
        APPROVAL_TOPIC,
        bootstrap_servers=os.environ.get("KAFKA_BROKERS", "localhost:9092"),
        group_id="delivery",
        auto_offset_reset="earliest",
    )
    await consumer.start()
    print("delivery ready", flush=True)
    try:
        async for message in consumer:
            envelope = Envelope.from_json(message.value)
            if envelope.type == MESSAGE_COMPOSED:
                print(envelope.payload["text"], flush=True)
                options = envelope.payload.get("options") or []
                for letter, option in zip("ABCDE", options):
                    print(f"  {letter}. {option}", flush=True)
            elif envelope.type == APPROVAL_REQUESTED:
                payload = envelope.payload
                print(
                    f"APPROVAL {payload.get('title', payload.get('action', 'action'))}",
                    flush=True,
                )
                for field in payload.get("fields") or []:
                    print(f"  {field['label']}: {field['value']}", flush=True)
                if not payload.get("fields"):
                    print(f"  Arguments: {payload.get('arguments', '')}", flush=True)
                if payload.get("consequences"):
                    print(f"  Consequences: {payload['consequences']}", flush=True)
                review = payload.get("review") or {}
                if review:
                    print(
                        f"  Review: {review.get('verdict')} - {review.get('reason')}",
                        flush=True,
                    )
                print(
                    f"  Decisions: {', '.join(payload.get('decisions', ['approve', 'deny']))}"
                    f" id={envelope.event_id}",
                    flush=True,
                )
            elif envelope.type == APPROVAL_RESOLVED:
                payload = envelope.payload
                edit = (
                    f" argument={payload['argument']!r}"
                    if payload.get("argument") is not None
                    else ""
                )
                print(
                    f"RESOLVED {payload['approval_id']} {payload['decision']}{edit}",
                    flush=True,
                )
            await consumer.commit()
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())
