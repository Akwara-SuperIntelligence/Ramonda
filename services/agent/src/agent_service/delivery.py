"""Delivery: the thinnest possible client.

Sources
    talk §04 — the client receives one boundary and renders it
    EDA §4.2 — `agent.message.composed`

Delta
    Printing is the whole client. A Slack or web client replaces this file and
    nothing else changes.
"""

from __future__ import annotations

import asyncio
import os

from aiokafka import AIOKafkaConsumer

from agent_service.events import MESSAGE_TOPIC, Envelope


async def main() -> None:
    consumer = AIOKafkaConsumer(
        MESSAGE_TOPIC,
        bootstrap_servers=os.environ.get("KAFKA_BROKERS", "localhost:9092"),
        group_id="delivery",
        auto_offset_reset="earliest",
    )
    await consumer.start()
    print("delivery ready", flush=True)
    try:
        async for message in consumer:
            envelope = Envelope.from_json(message.value)
            print(envelope.payload["text"], flush=True)
            await consumer.commit()
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())
