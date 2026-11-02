"""The run: one turn, durably orchestrated.

Sources
    talk §03 — a durable workflow, not a job queue: it resumes at the step that
               failed instead of replaying from the start
    talk §04 — the loop lives on the server, and the model only names tools
    lesson 02 — write the intent down before the effect, so a restart can
               continue rather than guess

Delta
    Temporal replaces the hand-rolled journal from lesson 02. This workflow is
    the journal: it holds control flow and nothing else. Every effect is an
    activity whose result is recorded in the event history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from agent_service.activities import ModelReply, ToolResult, call_model, run_tool


@dataclass
class RunRequest:
    """What starts a run."""

    conversation_id: str
    text: str
    max_steps: int = 6


@dataclass
class RunResult:
    """What a finished run returns."""

    conversation_id: str
    reply: str
    steps: int


@workflow.defn
class RunWorkflow:
    """One turn: model, tool, repeat, stop.

    Sources: talk §03 and §04; lesson 01.

    Delta: the loop is now a workflow, so a killed worker resumes here instead
    of losing the turn.
    """

    @workflow.run
    async def run(self, request: RunRequest) -> RunResult:
        history = [f"user: {request.text}"]
        run_id = workflow.info().workflow_id

        for step in range(request.max_steps):
            reply: ModelReply = await workflow.execute_activity(
                call_model,
                args=[step, history],
                start_to_close_timeout=timedelta(seconds=30),
            )

            if reply.kind == "final":
                return RunResult(
                    conversation_id=request.conversation_id,
                    reply=reply.text,
                    steps=step + 1,
                )

            result: ToolResult = await workflow.execute_activity(
                run_tool,
                args=[reply.tool, reply.argument, f"{run_id}:{step}"],
                start_to_close_timeout=timedelta(seconds=10),
            )
            history.append(f"tool {reply.tool}: {result.output}")

        raise ApplicationError(
            f"step budget exhausted after {request.max_steps} steps",
            non_retryable=True,
        )
