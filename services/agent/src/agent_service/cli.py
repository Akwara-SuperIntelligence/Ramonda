"""Start one turn and wait for its result.

Sources
    lesson 03 — the client carries a message and nothing else
    talk §04 — one boundary crosses to the server

Delta
    The client reads the next turn number from the store, so the workflow ID is
    `run:{conversation}:{seq}` and a second turn does not collide with the first.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from temporalio.client import Client

from agent_service.activities import next_seq
from agent_service.worker import TASK_QUEUE
from agent_service.workflow import RunRequest, RunWorkflow


async def start(conversation_id: str, text: str, org_id: str) -> None:
    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    client = await Client.connect(address)
    seq = await next_seq(org_id, conversation_id)
    handle = await client.start_workflow(
        RunWorkflow.run,
        RunRequest(conversation_id=conversation_id, text=text, seq=seq, org_id=org_id),
        id=f"run:{conversation_id}:{seq}",
        task_queue=TASK_QUEUE,
    )
    result = await handle.result()
    print(result.reply)


def main() -> None:
    parser = argparse.ArgumentParser(description="start one turn")
    parser.add_argument("text")
    parser.add_argument("--conversation", default="local")
    parser.add_argument("--org", default="local")
    args = parser.parse_args()
    asyncio.run(start(args.conversation, args.text, args.org))


if __name__ == "__main__":
    main()
