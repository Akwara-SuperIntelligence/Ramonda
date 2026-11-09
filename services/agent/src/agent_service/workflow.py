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
SEGMENT_STEPS = 20
MAX_TOKENS_DEFAULT = 400_000
MAX_SECONDS_DEFAULT = 8 * 60 * 60

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
        compact_steps,
        expire_approval,
        load_history,
        next_turn,
        create_task,
        finish_task,
        report_task,
        list_tasks,
        pin_prompt,
        plan_open,
        record_progress,
        record_run,
        release_lock,
        renew_lock,
        request_approval,
        reset_turn_state,
        review_action,
        routine_active,
        run_tool,
        save_tool_step,
        send_user,
        should_speak,
    )


@dataclass
class RunRequest:
    """What starts a turn, and what a continued segment carries."""

    conversation_id: str
    text: str
    org_id: str = "local"
    max_steps: int = 200
    kind: str = "user"  # "user", "helper", or "routine"
    failed: bool = False
    traceparent: str = ""
    routine_id: str = ""
    seq: int = -1
    step: int = 0
    tokens: int = 0
    continued: bool = False
    started_at: float = 0.0
    max_tokens: int = MAX_TOKENS_DEFAULT
    max_seconds: int = MAX_SECONDS_DEFAULT
    approval_timeout_minutes: int = 10


@dataclass
class RunResult:
    """What a finished turn returns."""

    conversation_id: str
    reply: str
    steps: int
    silent: bool = False
    stopped: bool = False
    budget_exhausted: bool = False


@dataclass
class HelperTask:
    """One delegated task."""

    org_id: str
    conversation_id: str
    parent_step: int
    prompt_version: str
    task_id: str
    task: str


HELPER_MAX_STEPS = 40


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

            if NEEDS_APPROVAL.get(reply.tool) or reply.tool == "update_plan":
                # The approval gate and the parent plan belong to the parent.
                history.append(
                    {
                        "role": "user",
                        "content": (
                            f"tool result: {reply.tool} denied "
                            "(helpers cannot change the parent plan or run"
                            " irreversible tools)"
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
        self._stopped = False
        self._stop_reason = ""
        self._continuing = False

    @workflow.signal
    def stop(self, reason: str = "") -> None:
        self._stopped = True
        self._stop_reason = reason or "stopped by user"

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
                execution_timeout=timedelta(hours=4),
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

    async def _finish_budget(
        self,
        request: RunRequest,
        run_id: str,
        seq: int,
        step: int,
        reason: str,
        stopped: bool = False,
    ) -> RunResult:
        text = (
            "Stopped at your request."
            if stopped
            else f"I reached the {reason} before I was sure the task was done."
        )
        await workflow.execute_activity(
            send_user,
            args=[
                request.org_id,
                request.conversation_id,
                seq,
                step + 1,
                request.text,
                text,
                f"{request.org_id}:{run_id}:{'stop' if stopped else 'budget'}",
                [],
                True,
                request.kind == "routine",
            ],
            start_to_close_timeout=timedelta(seconds=10),
        )
        await workflow.execute_activity(
            record_run,
            args=[
                request.org_id,
                request.conversation_id,
                run_id,
                "failed",
                False,
                reason,
                request.traceparent,
            ],
            start_to_close_timeout=timedelta(seconds=10),
        )
        return RunResult(
            conversation_id=request.conversation_id,
            reply=text,
            steps=step,
            silent=False,
            stopped=stopped,
            budget_exhausted=not stopped,
        )

    @workflow.run
    async def run(self, request: RunRequest) -> RunResult:
        run_id = workflow.info().workflow_id
        first = request.seq < 0
        started_at = request.started_at or workflow.now().timestamp()

        if request.kind == "routine" and first:
            active = await workflow.execute_activity(
                routine_active,
                args=[request.org_id, request.routine_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
            if not active:
                return RunResult(
                    conversation_id=request.conversation_id,
                    reply="",
                    steps=0,
                    silent=True,
                )

        while not await workflow.execute_activity(
            acquire_lock,
            args=[request.org_id, request.conversation_id, run_id],
            start_to_close_timeout=timedelta(seconds=10),
        ):
            await workflow.sleep(1)

        try:
            if first:
                await workflow.execute_activity(
                    record_run,
                    args=[
                        request.org_id,
                        request.conversation_id,
                        run_id,
                        "started",
                        False,
                        "",
                        request.traceparent,
                    ],
                    start_to_close_timeout=timedelta(seconds=10),
                )
            prompt_version: str = await workflow.execute_activity(
                pin_prompt,
                args=[request.org_id, request.conversation_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
            if first:
                seq: int = await workflow.execute_activity(
                    next_turn,
                    args=[request.org_id, request.conversation_id],
                    start_to_close_timeout=timedelta(seconds=10),
                )
                await workflow.execute_activity(
                    reset_turn_state,
                    args=[request.org_id, request.conversation_id],
                    start_to_close_timeout=timedelta(seconds=10),
                )
                await workflow.execute_activity(
                    compact,
                    args=[request.org_id, request.conversation_id],
                    start_to_close_timeout=timedelta(seconds=120),
                )
            else:
                seq = request.seq

            loaded = await workflow.execute_activity(
                load_history,
                args=[request.org_id, request.conversation_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
            history: list[dict] = loaded.messages
            memory_hash: str = loaded.memory_hash
            history.append({"role": "user", "content": request.text})
            step = request.step
            tokens = request.tokens
            last_signature: tuple[str, str] | None = None
            repeats = 0

            while step < request.max_steps:
                if self._stopped:
                    return await self._finish_budget(
                        request, run_id, seq, step, self._stop_reason, stopped=True
                    )

                elapsed = workflow.now().timestamp() - started_at
                if elapsed >= request.max_seconds:
                    return await self._finish_budget(
                        request,
                        run_id,
                        seq,
                        step,
                        f"time budget ({request.max_seconds}s)",
                    )
                if tokens >= request.max_tokens:
                    return await self._finish_budget(
                        request,
                        run_id,
                        seq,
                        step,
                        f"token budget ({request.max_tokens})",
                    )

                if step % SEGMENT_STEPS == 0:
                    if not await workflow.execute_activity(
                        renew_lock,
                        args=[request.org_id, request.conversation_id, run_id],
                        start_to_close_timeout=timedelta(seconds=10),
                    ):
                        raise ApplicationError(
                            "conversation lock lost", non_retryable=True
                        )

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
                tokens += reply.tokens

                if reply.kind != "final":
                    signature = (reply.tool, reply.argument)
                    if signature == last_signature:
                        repeats += 1
                    else:
                        last_signature = signature
                        repeats = 1
                    if repeats >= 3:
                        history.append(
                            {
                                "role": "user",
                                "content": (
                                    "You repeated the same tool call three times."
                                    " Change approach, or stop and explain the"
                                    " blocker."
                                ),
                            }
                        )
                        step += 1
                        repeats = 0
                        last_signature = None
                        continue

                if reply.kind == "final":
                    open_items: int = await workflow.execute_activity(
                        plan_open,
                        args=[request.org_id, request.conversation_id],
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                    if open_items and "blocked" not in reply.text.lower():
                        history.append(
                            {
                                "role": "user",
                                "content": (
                                    f"Your plan has {open_items} open item(s)."
                                    " Continue, or mark each item blocked with a"
                                    " reason. Do not answer yet."
                                ),
                            }
                        )
                        step += 1
                        continue
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
                            "",
                            request.traceparent,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                    return RunResult(
                        conversation_id=request.conversation_id,
                        reply=reply.text,
                        steps=step + 1,
                        silent=not speak,
                    )

                if request.kind == "routine" and NEEDS_APPROVAL.get(reply.tool):
                    denied = "routine turns cannot run irreversible tools"
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
                        {"role": "user", "content": f"tool result: {reply.tool} {denied}"}
                    )
                    step += 1
                    continue

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
                        step += 1
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
                    deadline = workflow.now() + timedelta(
                        minutes=request.approval_timeout_minutes
                    )
                    while self._decision is None and not self._stopped:
                        remaining = deadline - workflow.now()
                        if remaining <= timedelta(0):
                            break
                        chunk = min(remaining, timedelta(minutes=30))
                        try:
                            await workflow.wait_condition(
                                lambda: self._decision is not None or self._stopped,
                                timeout=chunk,
                            )
                        except asyncio.TimeoutError:
                            if workflow.now() >= deadline:
                                break
                            if not await workflow.execute_activity(
                                renew_lock,
                                args=[
                                    request.org_id,
                                    request.conversation_id,
                                    run_id,
                                ],
                                start_to_close_timeout=timedelta(seconds=10),
                            ):
                                raise ApplicationError(
                                    "conversation lock lost during approval",
                                    non_retryable=True,
                                )
                    if self._stopped:
                        return await self._finish_budget(
                            request,
                            run_id,
                            seq,
                            step,
                            self._stop_reason,
                            stopped=True,
                        )
                    decision = self._decision
                    if decision is None:
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
                        step += 1
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
                step += 1

                if step % SEGMENT_STEPS == 0 and step < request.max_steps:
                    open_items: int = await workflow.execute_activity(
                        plan_open,
                        args=[request.org_id, request.conversation_id],
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                    await workflow.execute_activity(
                        record_progress,
                        args=[
                            request.org_id,
                            request.conversation_id,
                            run_id,
                            step,
                            request.max_steps,
                            tokens,
                            open_items,
                            request.traceparent,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                    await workflow.execute_activity(
                        compact_steps,
                        args=[request.org_id, request.conversation_id, seq, step],
                        start_to_close_timeout=timedelta(seconds=120),
                    )
                    self._continuing = True
                    workflow.continue_as_new(
                        RunRequest(
                            conversation_id=request.conversation_id,
                            text=request.text,
                            org_id=request.org_id,
                            max_steps=request.max_steps,
                            kind=request.kind,
                            failed=request.failed,
                            traceparent=request.traceparent,
                            routine_id=request.routine_id,
                            seq=seq,
                            step=step,
                            tokens=tokens,
                            continued=True,
                            started_at=started_at,
                            max_tokens=request.max_tokens,
                            max_seconds=request.max_seconds,
                            approval_timeout_minutes=request.approval_timeout_minutes,
                        )
                    )

            return await self._finish_budget(
                request,
                run_id,
                seq,
                step,
                f"step budget ({request.max_steps} steps)",
            )
        except Exception as exc:
            if self._continuing:
                raise
            await workflow.execute_activity(
                record_run,
                args=[
                    request.org_id,
                    request.conversation_id,
                    run_id,
                    "failed",
                    False,
                    str(exc),
                    request.traceparent,
                ],
                start_to_close_timeout=timedelta(seconds=10),
            )
            raise
        finally:
            if not self._continuing:
                await workflow.execute_activity(
                    release_lock,
                    args=[request.org_id, request.conversation_id, run_id],
                    start_to_close_timeout=timedelta(seconds=10),
                )
