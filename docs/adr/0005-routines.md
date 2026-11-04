# 0005 — Routines

Status: accepted. Built as a CLI-only operator tool.

## Context

The agent could wake on a message, a helper report, or typing. It could not wake
on a clock, so the slide's "Routine at 8:00" trigger was missing. EDA §4.3
already says `UpdateRoutine` creates or changes a **Temporal Schedule**, so this
is not a Python cron loop.

## Decision

- A `routines` row holds `org_id`, `conversation_id`, `cron`, `timezone`, `text`,
  and `enabled`. Temporal is the executor; the row is the read model.
- Each routine is one Temporal Schedule with ID `routine:<routine_id>`. The
  schedule starts `RunWorkflow` with `RunRequest(kind="routine")`.
- Overlap policy is `SKIP`: a slow routine does not pile up runs.
- **CLI-only.** `routine.py` creates, lists, pauses, resumes, and deletes. There
  is no `UpdateRoutine` bus command until commands are authenticated (item 12).
- **No irreversible tools in a routine.** A scheduled turn has no human present,
  so the approval gate would wait ten minutes and expire. The workflow denies an
  approval tool with a tool result before the gate.
- **Routine turns speak.** A scheduled report is the point, so `should_speak`
  returns true for `kind="routine"` and the report does not consume the 24-hour
  helper budget.
- A routine that is missing or disabled is a no-op: the workflow checks
  `routine_active` before taking the lock.
- `delete.py` deletes the routine Schedules for a scope before deleting rows.

## Consequences

- Cron expressions and timezones are validated by Temporal and `zoneinfo`.
- A routine writes into its conversation, so the next message has the history.
- Deleting a conversation no longer leaves a firing schedule behind.
- The schedule is the source of truth for firing; the row is the source for
  "what is this routine".

## Deferred

- The `UpdateRoutine` bus command and a UI (needs auth).
- Per-user notification preferences for routine output.
- Pause on repeated failure. The policy currently skips overlaps only.
- Object storage for long routine output. That is still local files.