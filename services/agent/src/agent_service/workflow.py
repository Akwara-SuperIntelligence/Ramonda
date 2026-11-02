"""The run: one turn, durably orchestrated.

Sources
    talk §03 — a durable workflow, not a job queue: it resumes at the step that
               failed instead of replaying from the start
    talk §04 — the loop lives on the server, and the model only names tools
    talk §05 — the conversation is remembered outside the context window
    lesson 02 — write the intent down before the effect
    lesson 07 — memory has layers, and the log is one of them

Delta
    Temporal replaces the hand-rolled journal. History and the finished turn
    live in Postgres and arrive here as activity results, so the workflow stays
    deterministic and carries no transcript in its input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from agent_service.activities import (
        ModelReply,
        ToolResult,
        call_model,
        load_history,
        run_tool,
        send_user,
    )


@dataclass
class RunRequest:
    """What starts a turn."""

    conversation_id: str
    text: str
    seq: int = 0
    org_id: str = "local"
    max_steps: int = 6


@dataclass
class RunResult:
    """What a finished turn returns."""

    conversation_id: str
    reply: str
    steps: int


@workflow.defn
class RunWorkflow:
    """One turn: load, model, tool, repeat, save, stop.

    Sources: talk §03 and §04; lessons 01 and 07.
    """

    @workflow.run
    async def run(self, request: RunRequest) -> RunResult:
        history: list[str] = await workflow.execute_activity(
            load_history,
            args=[request.org_id, request.conversation_id],
            start_to_close_timeout=timedelta(seconds=10),
        )
        history.append(f"user: {request.text}")
        run_id = workflow.info().workflow_id

        for step in range(request.max_steps):
            reply: ModelReply = await workflow.execute_activity(
                call_model,
                args=[step, history],
                start_to_close_timeout=timedelta(seconds=30),
            )

            if reply.kind == "final":
                await workflow.execute_activity(
                    send_user,
                    args=[
                        request.org_id,
                        request.conversation_id,
                        request.seq,
                        request.text,
                        reply.text,
                        f"{request.org_id}:{run_id}:save",
                    ],
                    start_to_close_timeout=timedelta(seconds=10),
                )
                return RunResult(
                    conversation_id=request.conversation_id,
                    reply=reply.text,
                    steps=step + 1,
                )

            result: ToolResult = await workflow.execute_activity(
                run_tool,
                args=[reply.tool, reply.argument, f"{request.org_id}:{run_id}:{step}"],
                start_to_close_timeout=timedelta(seconds=10),
            )
            history.append(f"tool {reply.tool}: {result.output}")

        raise ApplicationError(
            f"step budget exhausted after {request.max_steps} steps",
            non_retryable=True,
        )
