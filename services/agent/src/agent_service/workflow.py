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
from typing import Any

from temporalio import workflow
from temporalio.exceptions import ApplicationError

HELPER_QUEUE = "agent-helper"

# Workflow-site tools act on child handles, so they live here, not in activities.
WORKFLOW_TOOL_NAMES = frozenset(
    {"delegate", "collect", "helpers", "message_helper", "stop_helper"}
)

with workflow.unsafe.imports_passed_through():
    from agent_service.activities import (
        NEEDS_APPROVAL,
        ModelReply,
        Review,
        ToolResult,
        acquire_lock,
        call_model,
        compact,
        expire_approval,
        load_history,
        next_turn,
        create_task,
        finish_task,
        report_task,
        list_tasks,
        pin_prompt,
        record_run,
        release_lock,
        request_approval,
        review_action,
        run_tool,
        save_tool_step,
        send_user,
        should_speak,
    )


@dataclass
class RunRequest:
    """What starts a turn."""

    conversation_id: str
    text: str
    org_id: str = "local"
    max_steps: int = 12
    kind: str = "user"  # "user" or "helper"
    failed: bool = False


@dataclass
class RunResult:
    """What a finished turn returns."""

    conversation_id: str
    reply: str
    steps: int
    silent: bool = False


@dataclass
class HelperTask:
    """One delegated task."""

    org_id: str
    conversation_id: str
    parent_step: int
    prompt_version: str
    task_id: str
    task: str


HELPER_MAX_STEPS = 5


@workflow.defn
class HelperWorkflow:
    """A sub-agent: fresh context, its own steps, a report back.

    Sources: talk §02 (sub-agents hand off to helpers with fresh context),
    talk §04 (helpers keep the main agent sparse), lesson 06 (a second loop).

    Delta: the helper shares the pinned prompt, so its prefix can hit the
    cache, and it records its model calls under a negative sequence so the
    parent transcript is untouched.
    """

    def __init__(self) -> None:
        self._stop = False
        self._messages: list[str] = []

    @workflow.signal
    def message(self, text: str) -> None:
        self._messages.append(text)

    @workflow.signal
    def stop(self) -> None:
        self._stop = True

    @workflow.run
    async def run(self, task: HelperTask) -> str:
        run_id = workflow.info().workflow_id
        history: list[dict] = [{"role": "user", "content": task.task}]

        for step in range(HELPER_MAX_STEPS):
            if self._stop:
                await workflow.execute_activity(
                    report_task,
                    args=[
                        task.org_id,
                        task.conversation_id,
                        task.task_id,
                        "stopped",
                        "stopped",
                    ],
                    start_to_close_timeout=timedelta(seconds=10),
                )
                return "stopped"
            for text in self._messages:
                history.append(
                    {"role": "user", "content": f"the main agent says: {text}"}
                )
            self._messages.clear()
            reply: ModelReply = await workflow.execute_activity(
                call_model,
                args=[
                    task.org_id,
                    task.conversation_id,
                    -(task.parent_step + 1),
                    step,
                    task.prompt_version,
                    "",
                    history,
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )
            if reply.kind == "final":
                await workflow.execute_activity(
                    report_task,
                    args=[
                        task.org_id,
                        task.conversation_id,
                        task.task_id,
                        "done",
                        reply.text,
                    ],
                    start_to_close_timeout=timedelta(seconds=10),
                )
                return reply.text

            if NEEDS_APPROVAL.get(reply.tool):
                # The approval gate belongs to the parent; helpers cannot act.
                history.append(
                    {
                        "role": "user",
                        "content": (
                            f"tool result: {reply.tool} denied "
                            "(helpers cannot run irreversible tools)"
                        ),
                    }
                )
                continue

            result: ToolResult = await workflow.execute_activity(
                run_tool,
                args=[
                    task.org_id,
                    task.conversation_id,
                    reply.tool,
                    reply.argument,
                    f"{run_id}:{step}",
                    task.task,
                ],
                start_to_close_timeout=timedelta(seconds=10),
            )
            history.append(
                {
                    "role": "user",
                    "content": f"tool result: {reply.tool} -> {result.output}",
                }
            )

        await workflow.execute_activity(
            report_task,
            args=[
                task.org_id,
                task.conversation_id,
                task.task_id,
                "failed",
                "helper step budget exhausted",
            ],
            start_to_close_timeout=timedelta(seconds=10),
        )
        return "helper step budget exhausted"


@workflow.defn
class RunWorkflow:
    """One turn: lock, load, model, tool, repeat, save, release.

    Sources: talk §03 and §04; lessons 01, 07, and 09.
    """

    def __init__(self) -> None:
        self._approval_id: str | None = None
        self._decision: str | None = None
        self._argument: str | None = None
        self._pending: dict[str, Any] = {}

    @workflow.signal
    def resolve(
        self, decision: str, approval_id: str, argument: str | None = None
    ) -> None:
        if approval_id == self._approval_id:
            self._decision = decision
            self._argument = argument

    async def _workflow_tool(
        self, reply: ModelReply, request: RunRequest, run_id: str, step: int, prompt_version: str
    ) -> str:
        if reply.tool == "delegate":
            helper_id = f"helper:{run_id}:{step}"
            task_id: str = await workflow.execute_activity(
                create_task,
                args=[request.org_id, request.conversation_id, reply.argument, helper_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
            handle = await workflow.start_child_workflow(
                HelperWorkflow.run,
                HelperTask(
                    org_id=request.org_id,
                    conversation_id=request.conversation_id,
                    parent_step=step,
                    prompt_version=prompt_version,
                    task_id=task_id,
                    task=reply.argument,
                ),
                id=helper_id,
                task_queue=HELPER_QUEUE,
                # The helper outlives the turn and reports by event.
                parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                execution_timeout=timedelta(minutes=30),
            )
            self._pending[task_id] = handle
            return f"started {task_id}"

        if reply.tool == "collect":
            ids = list(self._pending) if reply.argument == "all" else [reply.argument]
            lines = []
            for task_id in ids:
                child = self._pending.pop(task_id, None)
                if child is None:
                    lines.append(f"{task_id}: unknown task")
                    continue
                try:
                    report = await child
                except Exception as exc:
                    report = f"helper failed: {type(exc).__name__}"
                    await workflow.execute_activity(
                        finish_task,
                        args=[request.org_id, request.conversation_id, task_id, "failed", report],
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                lines.append(f"{task_id}: {report}")
            return "\n".join(lines) or "no tasks"

        if reply.tool == "helpers":
            return await workflow.execute_activity(
                list_tasks,
                args=[request.org_id, request.conversation_id],
                start_to_close_timeout=timedelta(seconds=10),
            )

        if reply.tool == "message_helper":
            task_id, _, text = reply.argument.partition(" ")
            child = self._pending.get(task_id)
            if child is None:
                return f"unknown task: {task_id}"
            await child.signal("message", text)
            return "sent"

        if reply.tool == "stop_helper":
            ids = list(self._pending) if reply.argument == "all" else [reply.argument]
            for task_id in ids:
                child = self._pending.get(task_id)
                if child is None:
                    continue
                await child.signal("stop")
                await workflow.execute_activity(
                    finish_task,
                    args=[request.org_id, request.conversation_id, task_id, "stopped", ""],
                    start_to_close_timeout=timedelta(seconds=10),
                )
            return f"stop sent: {reply.argument}"

        raise ApplicationError(f"unhandled workflow tool: {reply.tool}", non_retryable=True)

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
            await workflow.execute_activity(
                record_run,
                args=[request.org_id, request.conversation_id, run_id, "started"],
                start_to_close_timeout=timedelta(seconds=10),
            )
            prompt_version: str = await workflow.execute_activity(
                pin_prompt,
                args=[request.org_id, request.conversation_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
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
            loaded = await workflow.execute_activity(
                load_history,
                args=[request.org_id, request.conversation_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
            history: list[dict] = loaded.messages
            memory_hash: str = loaded.memory_hash
            history.append({"role": "user", "content": request.text})

            for step in range(request.max_steps):
                reply: ModelReply = await workflow.execute_activity(
                    call_model,
                    args=[
                        request.org_id,
                        request.conversation_id,
                        seq,
                        step,
                        prompt_version,
                        memory_hash,
                        history,
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                )

                if reply.kind == "final":
                    speak: bool = await workflow.execute_activity(
                        should_speak,
                        args=[
                            request.org_id,
                            request.conversation_id,
                            request.kind,
                            request.failed,
                            request.text,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                    )
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
                            reply.options,
                            speak,
                            request.kind == "helper",
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                    await workflow.execute_activity(
                        record_run,
                        args=[
                            request.org_id,
                            request.conversation_id,
                            run_id,
                            "completed",
                            not speak,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                    return RunResult(
                        conversation_id=request.conversation_id,
                        reply=reply.text,
                        steps=step + 1,
                        silent=not speak,
                    )

                if NEEDS_APPROVAL.get(reply.tool):
                    review: Review = await workflow.execute_activity(
                        review_action,
                        args=[
                            request.org_id,
                            request.conversation_id,
                            run_id,
                            step,
                            reply.tool,
                            reply.argument,
                            request.text,
                        ],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    if review.verdict == "deny":
                        denied = f"denied by reviewer: {review.reason}"
                        await workflow.execute_activity(
                            save_tool_step,
                            args=[
                                request.org_id,
                                request.conversation_id,
                                seq,
                                step + 1,
                                f"{reply.tool}({reply.argument}) -> {denied}",
                            ],
                            start_to_close_timeout=timedelta(seconds=10),
                        )
                        history.append(
                            {
                                "role": "user",
                                "content": f"tool result: {reply.tool} {denied}",
                            }
                        )
                        continue

                    approval_id = f"{request.org_id}:{run_id}:{step}:approval"
                    self._approval_id = approval_id
                    self._decision = None
                    self._argument = None
                    await workflow.execute_activity(
                        request_approval,
                        args=[
                            request.org_id,
                            request.conversation_id,
                            run_id,
                            reply.tool,
                            reply.argument,
                            approval_id,
                            review.verdict,
                            review.reason,
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
                    reply.argument = self._argument or reply.argument
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
                        history.append(
                            {
                                "role": "user",
                                "content": f"tool result: {reply.tool} denied ({decision})",
                            }
                        )
                        continue

                if reply.tool in WORKFLOW_TOOL_NAMES:
                    tool_out = await self._workflow_tool(
                        reply, request, run_id, step, prompt_version
                    )
                else:
                    result: ToolResult = await workflow.execute_activity(
                        run_tool,
                        args=[
                            request.org_id,
                            request.conversation_id,
                            reply.tool,
                            reply.argument,
                            f"{request.org_id}:{run_id}:{step}",
                            request.text,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                    tool_out = result.output

                await workflow.execute_activity(
                    save_tool_step,
                    args=[
                        request.org_id,
                        request.conversation_id,
                        seq,
                        step + 1,
                        f"{reply.tool}({reply.argument}) -> {tool_out}",
                    ],
                    start_to_close_timeout=timedelta(seconds=10),
                )
                history.append(
                    {
                        "role": "user",
                        "content": f"tool result: {reply.tool} -> {tool_out}",
                    }
                )

            raise ApplicationError(
                f"step budget exhausted after {request.max_steps} steps",
                non_retryable=True,
            )
        except Exception as exc:
            await workflow.execute_activity(
                record_run,
                args=[
                    request.org_id,
                    request.conversation_id,
                    run_id,
                    "failed",
                    False,
                    str(exc),
                ],
                start_to_close_timeout=timedelta(seconds=10),
            )
            raise
        finally:
            await workflow.execute_activity(
                release_lock,
                args=[request.org_id, request.conversation_id, run_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
