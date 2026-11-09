# What lives on the agent's computer

Status: design note. The sandbox is not built. This document records the
intended placement of every computer-bound capability and the temporary harness
fallback we use today.

Related: [BUILD §6.3](BUILD.md), [EDA §8](EDA.md), [ADR 0008](adr/0008-harness-first.md),
[ADR 0011](adr/0011-memory-files.md).

## The split

The **harness** is the brain: it runs the turn, calls the model, executes tool
calls, and enforces approvals. The **sandbox** is the agent's computer: a
disposable Linux machine with a filesystem, a shell, a browser, and a screen.

The rule from the talk is **everything is computer**. Files, skills, routines,
shell, browser, and screen belong on the computer. The harness only orchestrates.

## Inventory

| Capability | Today, in the harness | On the agent's computer | Status |
|---|---|---|---|
| Memory files | R2 objects, read by the service | `/home/agent/memory/` on the VM, synced to R2 | Files exist; VM not built |
| Transcript | `log/{seq}.jsonl` in R2 | `memory/log/`, one entry per turn | Files exist; VM not built |
| Profile facts | `profile.md` in R2 | `memory/profile.md`, read by the model | Files exist; VM not built |
| Tool facts | `facts-tool.md` in R2 | `memory/facts-tool.md`, tagged untrusted | Files exist; VM not built |
| Scratch | `scratch/{sha}.md` in R2 | `memory/scratch/`, one hour, deleted by the VM | Files exist; VM not built |
| Summary | `summary.json` in R2 | `memory/summary.json` | Files exist; VM not built |
| Turn plan | `plan.md` in R2 | `memory/plan.md`, read and written by the model | Files exist; VM not built |
| Working summary | `working.json` in R2 | `memory/working.json` for a long turn | Files exist; VM not built |
| Recall | Python substring scan over R2 | `grep -R` over `memory/`, or an index | Scan only |
| Search | Same scan | `rg`, `find`, `grep` on the VM | Not built |
| Skills | Repo `skills/`, read-only, `read_skill` | `/home/agent/skills/<name>/SKILL.md`, writable | Repo only |
| Many skills | Prompt names one skill | A skill index on the VM; read on demand | Not built |
| Routines | DB row plus a Temporal Schedule | `routines/<name>.md`; a sync creates the Schedule | DB only |
| File read | Artifacts and legacy local files | Any file in `/home/agent/` | Partial |
| File write | None | Any file in `/home/agent/` | Not built |
| Shell | None | `run_shell` inside the VM | Not built |
| Browser | None | Chrome in the VM, screen stream | Not built |
| Computer use | None | Screen and mouse in the VM | Not built |
| Inbound files | None | `/home/agent/inbox/`, then cards | Not built |
| Outbound files | None | `/home/agent/outbox/`, then cards | Not built |
| Binary files | None | LibreOffice, pandoc, Python in the VM | Not built |
| Learn by watching | None | Record a session, write a `SKILL.md` | Deferred, ADR 0009 |
| Snapshots | None | VM snapshot and restore | Not built |

## The contract

### Canonical and cache

- **R2 is canonical.** It holds memory, skills, and artifacts.
- **The VM is a cache and a workspace.** It is disposable. A lost VM is rebuilt
  from the golden image and the latest sync.
- A snapshot is not a system of record. It is a fast resume. R2 is the backup.

### Boot

1. The harness or the sandbox controller creates the VM from the golden image.
2. The VM syncs `memory/{org}/{conversation}/` from R2 to `/home/agent/memory/`.
3. Built-in skills mount read-only; writable skills sync to `/home/agent/skills/`.
4. Secrets arrive as short-lived leases from the secret broker. Never in the image.
5. Egress is denied by default. The VM gets the allowlist it needs.

### Turn

- The harness sends tool calls to the sandbox: `run_shell`, file operations,
  browser, screen.
- The model can `grep`, `cat`, `find`, and edit. That is why files beat a
  database for this layer.
- Large output stays in the VM or goes to R2. The context gets a path, not a blob.
- The conversation lock allows one VM per conversation at a time.

### Sleep and write-back

1. The VM writes changed memory files back to R2.
2. The VM snapshots for fast resume.
3. The VM stops. The next turn resumes from the snapshot or rebuilds and syncs.

If the VM dies before write-back, the last synced state survives. The lost work
is bounded by the sync interval, not the whole conversation.

### Conflicts

- One conversation, one active VM, one writer. The conversation lock enforces it.
- The sync is last-writer-wins per file. There is no merge.
- A file write is keyed by the effect token or the turn, so a retry replaces the
  same object rather than appending twice.

### Routines

A routine is a file in `routines/`, but the **schedule is not cron in the VM**.
The VM sleeps. Temporal owns the schedule and starts the turn. The routine file
holds the prompt and the cron expression. A sync creates or updates the Temporal
Schedule. The schedule must not depend on the VM being awake.

## What does not move to the computer

- **Temporal.** Durable execution, timers, approvals, schedules.
- **Kafka.** Commands and events.
- **Postgres.** Inbox, outbox, effects, approvals, locks, tasks, metrics, turn
  counter, prompt pin. Execution state, not memory.
- **Channels.** Delivery, choices, cards, typing.
- **Edge and identity.** Authentication and tenant context.
- **Quotas, metrics, health.** Service concerns.
- **The secret broker.** The VM gets leases, not secrets at rest.
- **MCP.** A tool source, not a computer. Deferred in ADR 0009.

## The current fallback

`transcript.py` emulates the workspace in R2:

- `load_history` reads the profile, facts, summary, scratch, and transcript.
- `recall` scans them in Python.
- `read_skill` reads the repo.
- Routines are a DB row and a Temporal Schedule.
- There is no shell, no browser, no screen, and no file write.

This is a compatibility layer. It is correct, but it is not the target. The
target is the VM above.

## Migration path

1. **Filesystem and shell.** Create the VM, sync memory, add `run_shell`,
   `read_file`, `write_file`, `list_files`. Switch `recall` to `grep`.
2. **Skills and routines.** Move writable skills to the VM. Sync routine files to
   Temporal. Add skill capture with human approval.
3. **Computer.** Browser, screen, mouse, inbound and outbound files, binary
   generation.

## Open

- One VM per conversation, or one VM per agent with several conversations?
- Sync on every write, or at checkpoints?
- Which path is the workspace root: `/home/agent` or `/workspace`?
- How long is a snapshot kept? What is the cost per snapshot?
- Does the VM run while waiting for approval, or sleep?
- What is the conflict policy if two turns somehow overlap?
