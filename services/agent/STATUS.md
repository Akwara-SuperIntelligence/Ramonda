# Agent service — status and handoff

Start here in a fresh session. This file records **state**, not history. The
design lives in [docs/EDA.md](../../docs/EDA.md) and
[docs/BUILD.md](../../docs/BUILD.md); do not duplicate it here.

## 1. What this service is

The always-on agent: one deployable containing the event consumer, the Temporal
orchestrator, and the harness. It owns conversations, episodic memory, run
orchestration, approvals, and delegation. It calls retrieval, the sandbox,
secrets, the LLM, and channels. Only the LLM exists, and it is called directly.

## 2. Run and verify

```
make up                                  # Postgres, Temporal, UI, Redpanda
make test                                # migrate + 71 tests
../../.venv/bin/python -m agent_service.worker      # both queues
../../.venv/bin/python -m agent_service.consumer
../../.venv/bin/python -m agent_service.relay
../../.venv/bin/python -m agent_service.delivery
```

State: **71 tests**; migrations through `015`, prompt version **8**. CI runs the
suite and the link check on every push. `make migrate` is safe to rerun.

The 3 live-model evals in the suite require a valid model key (OpenRouter via
`OPENROUTER_API_KEY`, or `DEEPSEEK_API_KEY`) and skip when none is present.

## 3. Where we came from

Oldest first. Each item is merged and tested.

| Step | What it bought |
|---|---|
| Durable turn | A turn resumes after `SIGKILL`; proved with 108 turns in flight |
| Real model | DeepSeek via OpenRouter behind an activity; the workflow never calls the network |
| Postgres state | `messages`, `effects` (idempotent per token), `inbox`, `outbox` |
| Event ingress | Kafka protocol via Redpanda; dedupe before the workflow |
| Reply as event | Outbox plus relay; `delivery.py` prints |
| Approval gate | `send_email` waits for a human; deadline; single-use resolution |
| Context engineering | cache measurement, compaction, long output to files, schema on demand, prompt pinning, pre-warm |
| Memory | facts and scratch, `recall`, folder skills with `SKILL.md` |
| Delegation | helper workflow, `delegate`/`collect`/`helpers`/`message_helper`/`stop_helper` |
| To-do list | `tasks` table, short ids (`t1`), status, report |
| Async helpers | the turn can end; the report arrives as `agent.helper.completed` |
| Reconciler | stale tasks fail after 35 minutes and report |
| Tool registry | one `ToolSpec` per tool; one handler each; agreement test |
| Auto-review | a second model checks an irreversible action; deny is a tool result |
| Typed approvals | structured card, edit-then-approve, `agent.approval.resolved` |
| Choice options | `options` on `agent.message.composed`; the card waits for channels |
| Live reviewer | allowed a birthday email; denied a password exfiltration |
| Untrusted tags | external tool output and helper reports are marked as data |
| Live injection | the model named the injected instruction and did not obey it |
| Silence | user turns speak; routine helper reports once a day; run events |
| Retention | hourly purge; windows in [ADR 0003](../../docs/adr/0003-retention-deletion-health.md) |
| Deletion | operator tool; hard delete with audit; refuses a busy conversation |
| Health | `/healthz` and `/readyz` on the worker and the consumer |
| Dead letters | poison commands go to `agent.commands.dlq`; replay tool |
| Metrics | the four numbers on `/metrics`; traceparent on run events |
| Quotas | interactive never dropped; routine/backfill capped per org |
| Routines | a Temporal Schedule starts a `kind="routine"` turn; CLI-only |
| Live routine | 08:00 Nairobi; next run 05:00 UTC; pause, resume, delete |
| Artifacts | long output and `read_file` use S3-compatible storage; opaque refs |

## 4. How it fits together

| File | Role |
|---|---|
| `workflow.py` | `RunWorkflow` (one turn) and `HelperWorkflow` (one delegated task) |
| `activities.py` | Effects, reviewer, approval payloads, trust tags, silence policy, run events, tools, prompts, memory, tasks |
| `consumer.py` | Kafka commands, typing, approval resolutions, helper completions, reaper, purge, dead letters |
| `relay.py` | Publishes the outbox |
| `delivery.py` | Reference client; prints messages, choices, and typed approvals |
| `health.py` | Liveness and readiness endpoints, plus `/metrics` |
| `metrics.py` | The four numbers as Prometheus text |
| `storage.py` | Artifact buckets: S3-compatible, local fallback, opaque refs |
| `maintenance.py` | Retention purge and scoped hard delete |
| `routines.py` | The routine row and its Temporal Schedule |
| `routine.py` | Operator CLI to create, list, pause, resume, and delete routines |
| `delete.py` | Operator CLI for deletion |
| `dlq.py` | Inspect and replay dead letters |
| `worker.py` | Two queues: `agent-orchestrator`, `agent-helper` |
| `events.py` | Envelope, event types, topics |
| `migrations/` | `001`–`015`, idempotent |
| `skills/<name>/SKILL.md` | Model-read skills |

## 5. What is left

The current plan is **harden first**:

| # | Item | Status |
|---|---|---|
| 1 | Auto-review before the human gate | **done** |
| 2 | Typed approvals, edit-then-approve | **done**: typed fields, field or whole-argument edit, choice options |
| 3 | Injection tagging at the boundary | **done**: external tool output, helper reports, memory provenance |
| 4 | Silence policy | **done**: 24h routine budget, failed/question reports speak, run events |
| 5 | Tracing + the four metrics | **done**: four numbers on `/metrics`; `traceparent` propagates; no OTel exporter yet |
| 6 | Quotas + priority | **partial**: interactive never dropped; routine/backfill capped; no preemption or batching yet |
| 7 | Retention, deletion, health, dead letters | **done**: hourly purge, scoped delete, health endpoints, DLQ |
| 8 | Evals gate in CI | **done**: tests and links; live model tests skip without a key |
| 9 | Sandbox client + contract | not started |
| 10 | Retrieval client + contract | not started |
| 11 | Secret broker | not started |
| 12 | Authenticated commands | not started |
| 13 | Real delivery client | not started |
| 14 | Routines / schedules | **done**: Temporal Schedule per routine, CLI-only |
| 15 | Object storage for artifacts | **done**: long output + `read_file`; opaque refs; local fallback in dev |

Permission approvals, the choice card itself, and custom rules are deferred.
The taxonomy, their fields, and their blockers are in
[ADR 0001](../../docs/adr/0001-interaction-kinds.md).

## 6. Known limits

- **Commands are unauthenticated.** Anyone who can publish to `agent.commands`
  can approve. The edge and identity provider are item 12.
- **Computer-dependent work is deferred.** `run_shell`, `browser`, and computer
  use need the sandbox (item 9). "Learn by watching" needs the sandbox and a
  skill-writing path; it is deferred in
  [ADR 0008](../../docs/adr/0008-harness-first.md) and
  [ADR 0009](../../docs/adr/0009-mcp-and-skill-capture.md).
- **Memory is in Postgres, not files.** EDA §8 describes profile and log files.
  The code uses the `memories` and `messages` tables. The storage decision is open.
- **MCP is not in the tool registry.** The tool list is fixed; a third-party tool
  is new code. MCP is deferred in
  [ADR 0009](../../docs/adr/0009-mcp-and-skill-capture.md).
- **Routines are CLI-only.** There is no `UpdateRoutine` bus command until
  commands are authenticated (item 12). A schedule is created by `routine.py`.
- **Routine turns cannot run irreversible tools.** No human is present to
  approve, so the workflow denies an approval tool before the gate.
- **Artifacts use a local fallback in development.** If `S3_BUCKET` is unset,
  bytes go to `.agent/artifacts`. A production deployment must set `S3_*` or it
  writes to ephemeral disk.
- **Artifacts are long tool output only.** Inbound and outbound chat attachments,
  file cards, and binary file generation are not built. Those need channels and
  the sandbox.
- **Artifact retention is 180 days.** `purge` deletes objects then rows. The
  bucket also needs a lifecycle rule; that is deployment configuration.
- **The consumer stops on an unhandled error.** The offset stays uncommitted and
  the bus redelivers. A poison command goes to `agent.commands.dlq`; a transient
  error does not diverge poison from retry.
- **`org_id` is a parameter, not a boundary.** No row-level security yet.
- **Prompt versions are frozen in code.** `PROMPTS` holds `1`–`8`; adding a
  prompt means adding a version, never editing an old one.
- **Untrusted tags are a prompt rule, not a boundary.** They mark text and tell
  the model to treat it as data. The human gate and the sandbox are separate guards.
- **Memory provenance is a heuristic.** A fact is `user` only when it appears
  verbatim in the user's message. A paraphrase is marked `tool`.
- **Silence uses a heuristic.** A helper report speaks on failure, on a question,
  or once per conversation per 24 hours. Tune it with evals.
- **Run events go to the outbox.** `delivery.py` does not print them; analytics
  and evals consume the topic later.
- **The reviewer is a filter, not a guarantee.** It is another model. It can be
  wrong in both directions. The human gate and the sandbox remain separate guards.
- **Only `send_email` has typed approval fields.** Any other action falls back to
  one editable `Arguments` field. Typed fields for a tool are data, not client code.
- **The choice card is data only.** `agent.message.composed` carries `options`,
  and the terminal prints them. A tappable card needs channels.
- **Permission approvals and custom rules are not built.** They need the sandbox
  and a policy store. See [ADR 0001](../../docs/adr/0001-interaction-kinds.md).
- **The prompt cache is size-gated** on DeepSeek. Below roughly 250 tokens there
  are no hits. Measurements are in [docs/CACHING.md](../../docs/CACHING.md).
- **Helpers are bounded** at 30 minutes and 5 steps; a task with no report after
  35 minutes is failed by the reaper and reported.
- **Memory is per conversation.** No cross-conversation profile yet.
- **Live evals are not in CI.** The unit suite and link check are gated. The
  live model tests skip when no valid model key is present.
- **Deletion is destructive and permanent.** It is an operator tool, not a bus
  command, until commands are authenticated (item 12). The audit row is the only record.
- **Purge runs in the consumer process.** A paused or scaled-down consumer does
  not purge. This is acceptable until there is a separate maintenance worker.
- **Quota drops, it does not queue.** A routine or backfill message over the cap
  is skipped and its offset commits. Interactive is never dropped. Preemption and
  batching come later.
- **Consumer lag is approximate.** It is the age of the newest run event, not a
  Kafka admin measurement.
- **Metrics use durations from the run events.** No OTel exporter runs yet; the
  ids are carried and the numbers are served as text.

## 7. Fresh-session checklist

1. Read this file, [`README.md`](README.md), [docs/EDA.md](../../docs/EDA.md)
   §4–5, and [docs/CACHING.md](../../docs/CACHING.md).
2. `make up && make test`. Do not build on a red suite.
3. Pick one item from section 5. Work in `services/agent/` only.
4. For every change: Sources/Delta in the module docstring, a migration if the
   schema moves, a test for the branch, a live check when it touches the model or
   the bus, then commit and push.

## 8. Suggested skills

Call these with the Skill tool when they apply:

- `ponytail` — for any code change.
- `code-review` — before merging a branch.
- `diagnosing-bugs` — when something hangs. Activities that fail on a missing
  table or an unregistered name look like waiting, not errors.
- `codebase-design` — when changing a module's interface.
- `writing-for-agents` — when editing skills or this file.
- `wait-what` — when an explanation did not land.

## 9. Conventions that keep this readable

- Every module states **Sources** (talk §, lesson) and **Delta** (what we add).
- Every side effect carries an **effect token**; a retry is a no-op.
- Write the **inbox after the effect**. A crash repeats an idempotent effect; it
  does not lose the command.
- Tools are declared once in `TOOL_SPECS`; the prompt, schema lookup, and
  approval policy derive from it.
- Auto-review is a filter before the human gate. Deny becomes a tool result;
  a reviewer failure escalates.
- Approval payloads are typed data. The client renders by `kind` and `fields`.
- External text is tagged `<untrusted>` and treated as data.
- Silence is a policy in the harness, not a model choice. A silent turn still
  stores its transcript and emits `agent.run.completed`.
- The outbox is the only way to publish; never write the database and publish
  separately.
- Workflow code is deterministic; all I/O is an activity.
