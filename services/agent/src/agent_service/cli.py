"""Start one turn and wait for its result.

Sources
    lesson 03 — the client carries a message and nothing else
    talk §04 — one boundary crosses to the server

Delta
    The client starts one turn with a unique ID. The turn number is read inside
    the workflow, under the conversation lock, so turns are serialised.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from uuid import uuid4

from temporalio.client import Client

from agent_service.worker import TASK_QUEUE
from agent_service.workflow import RunRequest, RunWorkflow


async def start(conversation_id: str, text: str, org_id: str) -> None:
    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    client = await Client.connect(address)
    handle = await client.start_workflow(
        RunWorkflow.run,
        RunRequest(conversation_id=conversation_id, text=text, org_id=org_id),
        id=f"turn:{uuid4().hex}",
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
