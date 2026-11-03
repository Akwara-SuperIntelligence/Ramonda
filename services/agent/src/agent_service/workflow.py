"""The run: one turn, durably orchestrated.

Sources
    talk §03 — a durable workflow, not a job queue: it resumes at the step that
               failed instead of replaying from the start
    talk §04 — the loop lives on the server, and the model only names tools
    talk §05 — the conversation is remembered outside the context window
    lesson 02 — write the intent down before the effect
    lesson 07 — memory has layers, and the log is one of them

Delta
    Temporal replaces the hand-rolled journal. The conversation lock is taken
    here, held for the whole turn, and released on exit, so one conversation
    has one turn at a time and the turn number is read under that lock.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from agent_service.activities import (
        NEEDS_APPROVAL,
        ModelReply,
        ToolResult,
        acquire_lock,
        call_model,
        compact,
        expire_approval,
        load_history,
        next_turn,
        release_lock,
        request_approval,
        run_tool,
        save_tool_step,
        send_user,
    )


@dataclass
class RunRequest:
    """What starts a turn."""

    conversation_id: str
    text: str
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
    """One turn: lock, load, model, tool, repeat, save, release.

    Sources: talk §03 and §04; lessons 01, 07, and 09.
    """

    def __init__(self) -> None:
        self._approval_id: str | None = None
        self._decision: str | None = None

    @workflow.signal
    def resolve(self, decision: str, approval_id: str) -> None:
        if approval_id == self._approval_id:
            self._decision = decision

    @workflow.run
    async def run(self, request: RunRequest) -> RunResult:
        run_id = workflow.info().workflow_id

        while not await workflow.execute_activity(
            acquire_lock,
            args=[request.org_id, request.conversation_id, run_id],
            start_to_close_timeout=timedelta(seconds=10),
        ):
            await workflow.sleep(1)

        try:
            seq: int = await workflow.execute_activity(
                next_turn,
                args=[request.org_id, request.conversation_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
            await workflow.execute_activity(
                compact,
                args=[request.org_id, request.conversation_id],
                start_to_close_timeout=timedelta(seconds=120),
            )
            history: list[str] = await workflow.execute_activity(
                load_history,
                args=[request.org_id, request.conversation_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
            history.append(f"user: {request.text}")

            for step in range(request.max_steps):
                reply: ModelReply = await workflow.execute_activity(
                    call_model,
                    args=[request.org_id, request.conversation_id, seq, step, history],
                    start_to_close_timeout=timedelta(seconds=30),
                )

                if reply.kind == "final":
                    await workflow.execute_activity(
                        send_user,
                        args=[
                            request.org_id,
                            request.conversation_id,
                            seq,
                            step + 1,
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

                if NEEDS_APPROVAL.get(reply.tool):
                    approval_id = f"{request.org_id}:{run_id}:{step}:approval"
                    self._approval_id = approval_id
                    self._decision = None
                    await workflow.execute_activity(
                        request_approval,
                        args=[
                            request.org_id,
                            request.conversation_id,
                            run_id,
                            reply.tool,
                            reply.argument,
                            approval_id,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                    try:
                        await workflow.wait_condition(
                            lambda: self._decision is not None,
                            timeout=timedelta(minutes=10),
                        )
                        decision = self._decision
                    except asyncio.TimeoutError:
                        decision = "expired"
                        await workflow.execute_activity(
                            expire_approval,
                            args=[approval_id],
                            start_to_close_timeout=timedelta(seconds=10),
                        )
                    if decision != "approved":
                        await workflow.execute_activity(
                            save_tool_step,
                            args=[
                                request.org_id,
                                request.conversation_id,
                                seq,
                                step + 1,
                                f"{reply.tool}({reply.argument}) -> denied ({decision})",
                            ],
                            start_to_close_timeout=timedelta(seconds=10),
                        )
                        history.append(f"tool {reply.tool}: denied ({decision})")
                        continue

                result: ToolResult = await workflow.execute_activity(
                    run_tool,
                    args=[reply.tool, reply.argument, f"{request.org_id}:{run_id}:{step}"],
                    start_to_close_timeout=timedelta(seconds=10),
                )
                await workflow.execute_activity(
                    save_tool_step,
                    args=[
                        request.org_id,
                        request.conversation_id,
                        seq,
                        step + 1,
                        f"{reply.tool}({reply.argument}) -> {result.output}",
                    ],
                    start_to_close_timeout=timedelta(seconds=10),
                )
                history.append(f"tool {reply.tool}: {result.output}")

            raise ApplicationError(
                f"step budget exhausted after {request.max_steps} steps",
                non_retryable=True,
            )
        finally:
            await workflow.execute_activity(
                release_lock,
                args=[request.org_id, request.conversation_id, run_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
