"""Inspect or replay one dead letter.

Sources
    EDA §12 — a poison event goes to a dead-letter topic and is replayed by hand
    BUILD §7 — dead-letter topics

Delta
    One message per run, from the `dlq-replay` consumer group. No replay without
    an explicit `--replay`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from agent_service.consumer import DLQ_TOPIC, TOPIC


async def main(replay: bool) -> None:
    consumer = AIOKafkaConsumer(
        DLQ_TOPIC,
        bootstrap_servers=os.environ.get("KAFKA_BROKERS", "localhost:9092"),
        group_id="dlq-replay",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    await consumer.start()
    try:
        try:
            message = await asyncio.wait_for(consumer.getone(), timeout=5)
        except asyncio.TimeoutError:
            print("dead-letter topic is empty")
            return
        try:
            data = json.loads(message.value)
        except json.JSONDecodeError:
            print(message.value.decode(errors="replace"))
            return
        print(json.dumps(data, indent=2))
        if not replay:
            return
        event = data.get("event")
        if not isinstance(event, dict) or "raw" in event:
            raise SystemExit("no replayable event in this dead letter")
        producer = AIOKafkaProducer(
            bootstrap_servers=os.environ.get("KAFKA_BROKERS", "localhost:9092")
        )
        await producer.start()
        try:
            await producer.send_and_wait(TOPIC, json.dumps(event).encode())
        finally:
            await producer.stop()
        await consumer.commit()
        print("replayed one message")
    finally:
        await consumer.stop()


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="inspect or replay one dead letter")
    parser.add_argument("--replay", action="store_true", help="publish the event again")
    args = parser.parse_args()
    asyncio.run(main(args.replay))


if __name__ == "__main__":
    main_cli()
