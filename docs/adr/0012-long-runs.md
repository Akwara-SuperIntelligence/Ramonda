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

## Consequences

- A turn can run for hours, across many Temporal runs, without a history blowup.
- The plan is the definition of done. It is a file, so a restart keeps it.
- A stop is cooperative: it lands at the next step, not mid-tool.
- Budget ceilings still stop a runaway model. They are visible, not silent.
- The stop signal cannot interrupt `collect` while it waits on a child.

## Open

- Per-org spend quotas and preemption policy beyond the stop signal.
- Helpers do not use `continue-as-new`; 40 steps is the current ceiling.
- The plan is per conversation. A plan shared across conversations needs an
  actor identity.
