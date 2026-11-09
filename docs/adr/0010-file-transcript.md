# 0010 — The transcript lives in files

Status: accepted. Messages left Postgres.

## Context

`messages` was the largest table and the read path for every turn. Postgres
cost grows with the transcript, and a read replica adds sync problems for data
that only one conversation writes. The talk says the transcript is memory and
memory can be files. Object storage is already in place for artifacts.

## Decision

- **One JSONL object per turn** under
  `memory/{org}/{conversation}/log/{seq}.jsonl`.
- Each line is an entry: `seq`, `step`, `role`, `content`, `created_at`.
- A write replaces the entry with the same `(step, role)`. A retry is a no-op.
- `send_user` writes the files first, then claims the effect and writes the
  outbox. A crash before the claim repeats an idempotent write.
- `next_turn` increments a counter in `conversations`. The workflow id makes a
  retry return the same number. A file-derived number would reset after a purge.
- `load_history` reads the turn objects after `summary_seq`.
- `compact` summarises entries from the files. The summary stays in
  `conversations`, which is small.
- `recall` scans the turn objects. There is no `grep` in object storage; at scale
  this needs an index or the sandbox.
- `delete_scope` deletes the conversation prefix. `purge` deletes objects older
  than 60 days by object time.
- Postgres keeps execution state: inbox, outbox, effects, approvals, locks,
  tasks, and metrics. Temporal still runs the turn.

**Why per turn, not per entry.** Object storage has no append. One object per
entry means many GETs per turn. One object per turn means one GET per turn for
the recent window, and a retry replaces the turn object instead of duplicating
entries. The turn object is small.

## What changed

- `transcript.py` is the new store, on top of `storage.py`.
- `migrations/016_drop_messages.sql` drops `messages`.
- `maintenance` purges and deletes transcript prefixes.
- The tests seed and assert through `transcript`, not SQL.

## Consequences

- The transcript no longer needs a read replica. R2 is strongly consistent.
- `recall` is a scan. It is correct now and will need an index later.
- Facts and scratch pad are still in Postgres. They are the next files to move.
- The local fallback under `.agent/` is for development and tests.
- Existing `messages` rows are not migrated. This is a pre-production cutover.

## Open

- Move facts, scratch, and the summary to files.
- A search index for the transcript, or sandbox `grep`.
- A one-off export for any environment that still holds `messages`.
