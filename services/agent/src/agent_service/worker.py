"""Worker entrypoint: run the loop on a server.

Sources
    talk §03 — the loop runs on a server and survives the laptop closing
    lesson 03 — the process is not the agent; state lives outside it

Delta
    The Temporal worker replaces the lesson's threaded HTTP server. The worker
    can die and restart without ending the turn.
"""

from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from agent_service.activities import call_model, run_tool
from agent_service.workflow import RunWorkflow

TASK_QUEUE = "agent-orchestrator"


async def main() -> None:
    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    client = await Client.connect(address)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[RunWorkflow],
        activities=[call_model, run_tool],
    )
    print(f"worker ready: {TASK_QUEUE} on {address}", flush=True)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
