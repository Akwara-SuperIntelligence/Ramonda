# 0012 — Long runs

Status: accepted. Phases 1–4 are built.

## Context

A turn stopped at 12 steps and failed when the budget ran out. The lock lasted
one hour. Compaction ran only between turns. The workflow passed the whole
history into every model call. None of that survives a task that runs for hours.

## Decision

### The model owns done; the harness owns safety

- The model writes `plan.md` with `update_plan`: `- [ ]` open, `- [x]` done.
- The harness injects the plan on every step.
- A `final` is accepted only when the plan has no open items, or the final text
  contains `blocked`.
- If items are open, the turn continues with a message that lists the open count.

### Budgets

Defaults: 200 steps, 400,000 tokens, 8 hours. They are safety ceilings, not the
normal stop. At the ceiling the run sends a final message and records `failed`
with the reason. It does not raise an exception.

`conversations.last_seq` and `last_workflow_id` make `next_turn` idempotent. The
workflow id makes a retry return the same turn number.

### Segments

- The loop runs until done or a ceiling.
- Every 20 steps: write progress, compact the middle of the turn, then
  `continue_as_new`.
- `RunRequest` carries `seq`, `step`, `tokens`, `started_at`, and the budgets.
- The new run reloads context from files. The workflow does not carry the
  transcript.
- The lock is renewed every segment and during a long approval wait. The same
  workflow id may re-acquire its own lock.

### Compaction inside a turn

`working.json` holds a summary of the middle of the current turn. The last six
steps stay in the context. `plan.md` and the transcript are unchanged. A new turn
clears `plan.md` and `working.json`.

### Interruption

- `RunWorkflow.stop` is a signal. It is checked at the next step and during an
  approval wait.
- A new user message in the same conversation signals the active run to stop
  before it starts the new turn. The new turn then waits for the lock.
- Approval wait defaults to 24 hours in the consumer. The lock is renewed in
  30-minute chunks while waiting.

### Helpers

- 40 steps, 4-hour execution timeout.
- A helper cannot change the parent plan or run an irreversible tool.

### Observability

- `agent.run.progress` events every segment carry step, budget, tokens, and open
  plan items.
- `/metrics` adds `agent_tokens_total` for the last 7 days.

### Prompt

Version 9 adds `update_plan` and the long-run rules. Versions 1–8 stay frozen.

## Limits

- **A stop is cooperative.** It lands at the next step, not mid-tool. It cannot
  interrupt `collect` while it waits on a child.
- **Context is rebuilt per segment**, every 20 steps. It is not assembled inside
  the model activity on every call.
- **Budgets are ceilings.** 200 steps, 400,000 tokens, 8 hours. At the ceiling the
  turn sends a final and records `failed`; it does not raise.
- **The token budget is not a dollar budget.** `agent_tokens_total` is the spend
  signal for the last 7 days. Per-org dollar quotas are not built.
- **The plan and working summary are per conversation.** A new turn clears both.
  A cross-conversation plan needs an actor identity.
- **Helpers are shorter.** 40 steps, 4 hours, no `continue-as-new`. The task
  reaper fails a silent helper after 4 hours 5 minutes.
- **Prompt v9 is the long-run prompt.** A conversation pinned to v8 has no
  `update_plan` and no plan gate; it still has the higher budgets.
- **Approval waits default to 24 hours** in the consumer. The lock is renewed in
  30-minute chunks. If the lock is lost, the run fails.
- **Progress is per segment**, not per step.

## Open

- Per-org spend quotas and preemption policy beyond the stop signal.
- Helpers do not use `continue-as-new`; 40 steps is the current ceiling.
- The plan is per conversation. A plan shared across conversations needs an
  actor identity.
