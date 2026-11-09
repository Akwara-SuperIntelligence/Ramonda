# 0011 — Facts, scratch, and the summary live in files

Status: accepted. All agent memory is now files.

## Context

ADR 0010 moved the transcript out of Postgres. Facts, scratch notes, and the
compaction summary were still rows in `memories` and `conversations`. The talk
shows `memory/profile.md` and dated facts as plain files. Postgres is execution
state, not memory.

## Decision

All memory lives under `memory/{org}/{conversation}/`:

| File | Holds | Read when |
|---|---|---|
| `profile.md` | User facts, one per line | Every turn, trusted |
| `facts-tool.md` | Tool facts, one per line | Every turn, untrusted |
| `scratch/{sha}.md` | One note per effect token | This hour |
| `summary.json` | `{"text": ..., "seq": ...}` | Every turn |
| `log/{seq}.jsonl` | The transcript, one object per turn | Recent window |

- **Two fact files, not one.** Provenance decides the prompt section. User facts
  are trusted. Tool facts are wrapped as `<untrusted>`. A single `profile.md`
  would lose that distinction.
- **Facts are line appends.** `remember` adds `- fact` to the correct file. A
  duplicate line is a no-op. Newlines in a fact become spaces.
- **Scratch is one object per effect token.** The key is a hash of the token, so
  a retry replaces the same note. `load_scratch` filters by object time to one
  hour. `purge_scratch` removes older notes.
- **The summary is JSON.** `compact` reads the transcript, writes
  `summary.json` with the cutoff, and no longer touches `conversations`.
- **Delete is a prefix.** `delete_scope` removes the whole conversation folder:
  log, profile, tool facts, scratch, summary.
- **Retention is selective.** `purge` deletes only `log/` objects older than 60
  days. Facts, the profile, and the summary are kept. `purge_scratch` deletes
  scratch older than one hour.
- **Temporal still runs the turn.** The workflow calls activities; the
  activities read and write files. Workflow history gets paths and small text,
  not file bodies.

`migrations/017_memory_files.sql` drops `memories` and the `summary` and
`summary_seq` columns.

## Consequences

- Postgres holds only execution state: inbox, outbox, effects, approvals, locks,
  tasks, metrics, and the turn counter.
- These files are the sandbox workspace. The intended placement, sync, and
  lifecycle are in [AGENT-COMPUTER.md](../AGENT-COMPUTER.md).
- `recall` reads the profile, the tool facts, the scratch files, and the
  transcript. It is a scan. At scale it needs an index or the sandbox.
- The profile is per conversation. A cross-conversation user profile needs an
  actor identity, which the harness does not pass yet.
- Existing `memories` rows are not migrated. This is a pre-production cutover.

## Open

- An actor-level profile shared by conversations.
- A search index for memory and transcript.
- A one-off export for any environment that still holds `memories`.
