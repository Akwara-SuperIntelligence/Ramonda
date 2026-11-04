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

from agent_service.activities import (
    acquire_lock,
    call_model,
    compact,
    create_task,
    expire_approval,
    finish_task,
    list_tasks,
    load_history,
    next_turn,
    pin_prompt,
    release_lock,
    report_task,
    request_approval,
    review_action,
    run_tool,
    save_tool_step,
    send_user,
)
from agent_service.workflow import HELPER_QUEUE, HelperWorkflow, RunWorkflow

TASK_QUEUE = "agent-orchestrator"
HELPER_QUEUE = "agent-helper"

ACTIVITIES = [
    acquire_lock,
    call_model,
    compact,
    create_task,
    expire_approval,
    finish_task,
    list_tasks,
    load_history,
    next_turn,
    pin_prompt,
    release_lock,
    report_task,
    request_approval,
    review_action,
    run_tool,
    save_tool_step,
    send_user,
]


async def main() -> None:
    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    client = await Client.connect(address)
    workers = [
        Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[RunWorkflow],
            activities=ACTIVITIES,
        ),
        Worker(
            client,
            task_queue=HELPER_QUEUE,
            workflows=[HelperWorkflow],
            activities=ACTIVITIES,
        ),
    ]
    print(f"worker ready: {TASK_QUEUE} + {HELPER_QUEUE} on {address}", flush=True)
    await asyncio.gather(*(worker.run() for worker in workers))


if __name__ == "__main__":
    asyncio.run(main())
