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
    compact_steps,
    create_task,
    expire_approval,
    finish_task,
    list_tasks,
    load_history,
    next_turn,
    pin_prompt,
    plan_open,
    record_progress,
    record_run,
    release_lock,
    renew_lock,
    report_task,
    request_approval,
    reset_turn_state,
    review_action,
    routine_active,
    run_tool,
    save_tool_step,
    send_user,
    should_speak,
)
from agent_service.health import start_health_server
from agent_service.workflow import HELPER_QUEUE, HelperWorkflow, RunWorkflow

TASK_QUEUE = "agent-orchestrator"
HELPER_QUEUE = "agent-helper"

ACTIVITIES = [
    acquire_lock,
    call_model,
    compact,
    compact_steps,
    create_task,
    expire_approval,
    finish_task,
    list_tasks,
    load_history,
    next_turn,
    pin_prompt,
    plan_open,
    record_progress,
    record_run,
    release_lock,
    renew_lock,
    report_task,
    request_approval,
    reset_turn_state,
    review_action,
    routine_active,
    run_tool,
    save_tool_step,
    send_user,
    should_speak,
]


async def main() -> None:
    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    start_health_server(int(os.environ.get("HEALTH_PORT", "8080")), "worker")
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
