"""Start one turn and wait for its result.

Sources
    lesson 03 — the client carries a message and nothing else
    talk §04 — one boundary crosses to the server

Delta
    A command replaces the lesson's HTTP client. The boundary is the same: the
    client sends text and receives text.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from temporalio.client import Client

from agent_service.worker import TASK_QUEUE
from agent_service.workflow import RunRequest, RunWorkflow


async def start(conversation_id: str, text: str) -> None:
    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    client = await Client.connect(address)
    handle = await client.start_workflow(
        RunWorkflow.run,
        RunRequest(conversation_id=conversation_id, text=text),
        id=f"run:{conversation_id}:0",
        task_queue=TASK_QUEUE,
    )
    result = await handle.result()
    print(result.reply)


def main() -> None:
    parser = argparse.ArgumentParser(description="start one turn")
    parser.add_argument("text")
    parser.add_argument("--conversation", default="local")
    args = parser.parse_args()
    asyncio.run(start(args.conversation, args.text))


if __name__ == "__main__":
    main()
