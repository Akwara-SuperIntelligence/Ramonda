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

from agent_service import activities
from agent_service.activities import call_model, run_tool
from agent_service.workflow import RunRequest, RunWorkflow

TASK_QUEUE = "test"


def _fake_model(monkeypatch, *replies: str) -> None:
    """Answer each model call from a script, so tests never touch the network."""
    script = iter(replies)
    monkeypatch.setattr(
        activities,
        "_post",
        lambda payload: {"choices": [{"message": {"content": next(script)}}]},
    )


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


def test_a_turn_runs_one_tool_then_answers(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_EFFECTS_DIR", str(tmp_path))
    _fake_model(monkeypatch, '{"tool": "echo", "argument": "hello"}', '{"final": "done"}')

    result = asyncio.run(_run(RunRequest("c1", "hello")))

    assert result.conversation_id == "c1"
    assert result.steps == 2
    assert result.reply == "done"
    assert len(list(tmp_path.iterdir())) == 1


def test_a_duplicate_token_writes_once(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_EFFECTS_DIR", str(tmp_path))

    asyncio.run(run_tool("echo", "first", "run:c1:0"))
    asyncio.run(run_tool("echo", "second", "run:c1:0"))

    markers = list(tmp_path.iterdir())
    assert len(markers) == 1
    assert markers[0].read_text() == "first"


def test_step_budget_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_EFFECTS_DIR", str(tmp_path))
    _fake_model(monkeypatch, '{"tool": "echo", "argument": "hello"}')

    with pytest.raises(WorkflowFailureError):
        asyncio.run(_run(RunRequest("c1", "hello", max_steps=1)))
