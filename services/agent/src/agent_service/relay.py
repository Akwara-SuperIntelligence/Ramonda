"""Publish queued messages from the outbox.

Sources
    EDA §5 — outbox instead of a dual write
    EDA §4.2 — `agent.message.composed` is what clients consume

Delta
    The reply is now an event. A relay publishes unpublished rows and marks
    them, so a crash republishes rather than drops.
"""

from __future__ import annotations

import asyncio
import os

import psycopg
from aiokafka import AIOKafkaProducer

from agent_service.activities import _dsn


async def relay_once(producer) -> int:
    """Publish one batch. Returns how many rows were sent."""
    async with await psycopg.AsyncConnection.connect(_dsn()) as conn:
        async with conn.transaction():
            cursor = await conn.execute(
                "select id, topic, payload from outbox"
                " where published_at is null order by created_at limit 100"
                " for update skip locked"
            )
            rows = await cursor.fetchall()
            for row_id, topic, payload in rows:
                await producer.send_and_wait(topic, payload.encode())
                await conn.execute(
                    "update outbox set published_at = now() where id = %s", (row_id,)
                )
    return len(rows)


async def main() -> None:
    producer = AIOKafkaProducer(
        bootstrap_servers=os.environ.get("KAFKA_BROKERS", "localhost:9092")
    )
    await producer.start()
    print("relay ready", flush=True)
    try:
        while True:
            sent = await relay_once(producer)
            await asyncio.sleep(0.2 if sent else 1)
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
