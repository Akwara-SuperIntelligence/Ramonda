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
make test                                # migrate + 46 tests
../../.venv/bin/python -m agent_service.worker      # both queues
../../.venv/bin/python -m agent_service.consumer
../../.venv/bin/python -m agent_service.relay
../../.venv/bin/python -m agent_service.delivery
```

State: **46 tests**, 4 of them live model tests; migrations through `011`;
prompt version **7**. CI runs the suite and the link check on every push.
`make migrate` is safe to rerun.

## 3. Where we came from

Oldest first. Each item is merged and tested.

| Step | What it bought |
|---|---|
| Durable turn | A turn resumes after `SIGKILL`; proved with 108 turns in flight |
| Real model | DeepSeek behind an activity; the workflow never calls the network |
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

## 4. How it fits together

| File | Role |
|---|---|
| `workflow.py` | `RunWorkflow` (one turn) and `HelperWorkflow` (one delegated task) |
| `activities.py` | All effects, the reviewer, approval payloads, the tool handlers, prompt versions, memory, tasks |
| `consumer.py` | Kafka commands, typing, approval resolutions, helper completions, reaper loop |
| `relay.py` | Publishes the outbox |
| `delivery.py` | Reference client; prints messages, choices, and typed approvals |
| `worker.py` | Two queues: `agent-orchestrator`, `agent-helper` |
| `events.py` | Envelope, event types, topics |
| `migrations/` | `001`–`011`, idempotent |
| `skills/<name>/SKILL.md` | Model-read skills |

## 5. What is left

The current plan is **harden first**:

| # | Item | Status |
|---|---|---|
| 1 | Auto-review before the human gate | **done** |
| 2 | Typed approvals, edit-then-approve | **done**: typed fields, field or whole-argument edit, choice options |
| 3 | Injection tagging at the boundary | not started |
| 4 | Silence policy | not started |
| 5 | Tracing + the four metrics | partial: tokens and cache only |
| 6 | Quotas + priority | not started |
| 7 | Retention, deletion, health, dead letters | not started |
| 8 | Evals gate in CI | **done**: tests and links; live model tests skip without a key |
| 9 | Sandbox client + contract | not started |
| 10 | Retrieval client + contract | not started |
| 11 | Secret broker | not started |
| 12 | Authenticated commands | not started |
| 13 | Real delivery client | not started |

Permission approvals, the choice card itself, and custom rules are deferred.
The taxonomy, their fields, and their blockers are in
[ADR 0001](../../docs/adr/0001-interaction-kinds.md).

## 6. Known limits

- **Commands are unauthenticated.** Anyone who can publish to `agent.commands`
  can approve. The edge and identity provider are item 12.
- **The consumer stops on an unhandled error.** The offset stays uncommitted and
  the bus redelivers. There is no dead-letter topic yet; that is item 7.
- **`org_id` is a parameter, not a boundary.** No row-level security yet.
- **Prompt versions are frozen in code.** `PROMPTS` holds `1`–`7`; adding a
  prompt means adding a version, never editing an old one.
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
  four live model tests skip without `DEEPSEEK_API_KEY`.

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
- The outbox is the only way to publish; never write the database and publish
  separately.
- Workflow code is deterministic; all I/O is an activity.
