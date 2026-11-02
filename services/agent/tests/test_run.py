"""Behaviour of one turn.

Sources
    lesson 01 — a turn is three steps, repeated
    lesson 02 — a failure must not cost the turn its state

Delta
    The time-skipping test environment replaces a running Temporal server, so
    the workflow and its activities run exactly as the worker runs them.
"""

from __future__ import annotations

import asyncio

import pytest
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agent_service.activities import call_model, run_tool
from agent_service.workflow import RunRequest, RunWorkflow

TASK_QUEUE = "test"


async def _run(request: RunRequest, workflow_id: str = "run:c1:0"):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[RunWorkflow],
            activities=[call_model, run_tool],
        ):
            return await env.client.execute_workflow(
                RunWorkflow.run,
                request,
                id=workflow_id,
                task_queue=TASK_QUEUE,
            )


def test_a_turn_runs_one_tool_then_answers():
    result = asyncio.run(_run(RunRequest("c1", "hello")))

    assert result.conversation_id == "c1"
    assert result.steps == 2
    assert result.reply == "done in 2 context entries"


def test_step_budget_is_enforced():
    with pytest.raises(WorkflowFailureError):
        asyncio.run(_run(RunRequest("c1", "hello", max_steps=1)))
