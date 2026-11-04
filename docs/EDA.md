# EDA: the agent service in an event-driven system

Scope: **one service** — the always-on agent — as a participant in a larger
microservice, event-driven system. Not the organisation ingestion pipeline, not
the graph-vector store, not the channels. The agent's internals are in
[ACHITECTURE.md](ACHITECTURE.md) and
[reference/architecture-map.html](../reference/architecture-map.html); the
Rust/Python split is in [LANGUAGE.md](LANGUAGE.md); the full service inventory is
in [BUILD.md](BUILD.md). Vocabulary follows [GLOSSARY.md](../GLOSSARY.md).

The service keeps the shape from the talk: thin client, thick server, one
`send_user` boundary, one durable run per turn, a disposable computer, memory as
files, and an approval gate on irreversible actions. What changes is **who owns
what**, **how the outside world reaches the loop**, and **how one codebase is
deployed for customers with different isolation requirements**.

## 0. Decisions at a glance

| # | Decision | Choice | Why |
|---|---|---|---|
| 1 | Transport between services | Kafka protocol (Redpanda or managed) | Replayable log, partition ordering, consumer groups |
| 2 | Orchestration inside this service | Temporal, private | Long runs resume at the failed step |
| 3 | External contract | Events out, commands in | No workflow IDs outside the service |
| 4 | Dedupe | Three layers: inbox, workflow ID, effect token | Every hop is at-least-once |
| 5 | Writes plus publish | Transactional outbox | No dual-write inconsistency |
| 6 | Waiting on other services | Subscription table plus signal | Never poll |
| 7 | Organisation knowledge | HelixDB, behind a retrieval service | Ingestion owns the write path |
| 8 | Identity | OIDC provider (Zitadel or Keycloak) | One login path, no per-client code |
| 9 | Deployment | Shared cell, dedicated stamp, or BYOC | One codebase, three topologies |
| 10 | Ordering | Partition by `org_id` | Per-conversation order is the requirement |

## 1. Where this service ends

| This service owns | This service calls |
|---|---|
| Conversation and message state | Retrieval service (reads HelixDB) |
| Episodic memory: profile, dated logs, scratchpad, skills | Sandbox control plane (Rust) |
| Run orchestration and harness policy | Secret broker and egress proxy |
| Approval policy and pending approvals | LLM gateway (limits, cost attribution) |
| Tool surface offered to the model | Identity provider (token validation) |
| Evals over its own traces | Channels and delivery |

Three rules follow, and they are load-bearing:

- **The agent never writes the graph-vector store.** Ingestion owns that write
  path. The agent reads through retrieval and emits observations as events if
  anyone wants them.
- **The agent never links the HelixDB SDK.** It calls the retrieval service over
  HTTP. A database client inside the harness couples the agent to another team's
  schema and forces a redeploy when their model changes.
- **No other service knows about Temporal.** No workflow IDs in payloads, no
  signalling our runs from outside, no querying our workflows for status. Status
  is a domain event or a read model.

## 2. Deployment profiles

One codebase, one artifact set, three topologies. This is the answer to "can a
bank have its own deployment without a fork".

| Profile | Customer | Isolation | Operational cost |
|---|---|---|---|
| **Shared cell** | Self-serve, SMB | `org_id` plus row-level security plus Helix `tenant_id` | One upgrade serves every tenant |
| **Dedicated stamp** | Mid-market, regulated | Own database, bucket, keys, Temporal namespace | One deployment per customer, one upgrade path |
| **BYOC / on-prem** | Tier-1 banks, government | Customer's cloud account and network | Customer operates; we ship images and a chart |

Rules:

- Every service must run in all three profiles. A service that only runs shared
  couples the product to one business model.
- A tenant is a row in a cell and the whole deployment in a stamp. Same binary,
  same migrations.
- Customisation is configuration, policy, and adapters. Never a fork, never a
  per-client branch.
- Dedicated is a premium SKU. Price it to fund fleet operations: many
  deployments mean many upgrades.
- The test: deploy the whole system into a fresh cloud account with one command
  and one config file. If that fails, neither multi-tenancy nor a fork will save
  the deal.

## 3. Two layers, one owner per process

```
 other services ──events──▶ bus ──▶ consumer ──▶ Temporal ──▶ harness worker
        ▲                  │  dedupe, order,    (private)         │
        │                  │  quota, priority                     │
        └── domain events ─┴──────── outbox ◀──────── Postgres ◀──┘

 platform, shared:  sandbox (Rust) · secrets (Rust) · LLM gateway · channels
 external:          identity provider · retrieval API → HelixDB ← ingestion
```

- The **bus** carries facts between services. It is a log, not a task queue.
- **Temporal** carries control flow inside this service.
- **One owner per long-running process.** If a process spans services, exactly
  one workflow owns it and calls the other services' idempotent commands. Never
  encode "and then, and then" as a chain of events — that is a saga nobody can
  trace, cancel, or replay.
- **Events for facts, workflows for processes.** The bus says what happened. It
  never says what to do next.

Backpressure is a feature of this split: when the service is saturated, the bus
buffers and you observe **consumer lag**, not request errors. Alert on lag, not
on 5xx.

## 4. Contracts

### 4.1 Event envelope

Stable, additive-only, versioned per type. Keep it small; put bulk data in object
storage and pass a URI.

```jsonc
{
  "event_id":       "01J...",          // ULID, unique per emission
  "type":           "agent.run.completed",
  "version":        1,                  // per type, additive changes only
  "occurred_at":    "2026-11-02T10:00:00Z",
  "producer":       "agent-service",
  "org_id":         "org_123",          // tenant; also the partition key
  "actor_id":       "user_456",         // who or what caused it
  "subject":        { "conversation_id": "conv_789", "run_id": "run_abc" },
  "correlation_id": "01J...",           // the causal chain
  "causation_id":   "01J...",           // the command/event that caused this
  "priority":       "interactive",      // interactive | routine | backfill
  "traceparent":    "00-...-...-01",
  "payload":        { }
}
```

Rules: `event_id` is never reused; `type` is namespaced `agent.<noun>.<verb>`;
`payload` is schema-validated in CI; consumers ignore unknown fields and tolerate
unknown types.

### 4.2 Events published

| Event | When | Consumed by |
|---|---|---|
| `agent.message.composed` | The agent wants to say something; carries text plus presentation hints | Channels and delivery |
| `agent.run.started` | A run begins | Analytics, UI read models |
| `agent.run.completed` | Final answer or deliberate silence | Evals, analytics |
| `agent.run.failed` | Terminal failure, with reason class | On-call, evals |
| `agent.approval.requested` | A gate needs a human | Approvals UI, notifications |
| `agent.approval.resolved` | Approved or denied | Audit |
| `agent.observation.recorded` | A durable fact worth sharing | Ingestion (optional) |

Do **not** emit an event per tool call or per model call. That is trace data, not
domain data; it belongs in spans. The bus is for facts other services act on.

### 4.3 Commands accepted

| Command | Caller | Effect |
|---|---|---|
| `SendMessage` | Channels | Signal an active run, or start one |
| `CancelRun` | UI, policy | Graceful yield, then cancel |
| `ResolveApproval` | Approvals service | Unblocks a waiting gate |
| `UpdateRoutine` | UI, admin | Create or change a Temporal Schedule |
| `Typing` | Clients | Warm the pinned prompt prefix; no turn starts |

Commands are idempotent on `command_id`, carry a reply event, and are the only
write path from outside. Everything else is read-only.

### 4.4 Tool surface

The model's tools are the narrow waist: `run_shell`, `send_user`, `remember`,
`recall`, `delegate`, `retrieve`, `browser`. `send_user` is the only tool that
crosses the product boundary, which is why channel changes never touch the
harness. `retrieve` is the only door to organisational knowledge.

## 5. Exactly-once is a lie; here are the dedupe layers

| Layer | Mechanism | Catches |
|---|---|---|
| Inbox | `inbox(event_id)` unique constraint, written after the idempotent effect | A second handling after a crash |
| Workflow | Workflow ID `turn:{event_id}`; an already-started reply is success | Duplicate starts |
| Conversation | `conversation_locks` row held for the whole turn | Two turns at once on one conversation |
| Effect | Effect token `sha256(run_id, step_index, tool_name)` on every side effect | Activity retry |
| Approval | `update ... where status = 'pending'` plus the stored decision; a repeat signal is safe | Replayed approval |

- **Outbox.** Write product state and the outgoing event in one Postgres
  transaction; a relay or CDC publishes. Never publish from the workflow body,
  and never write the database and publish as two separate steps.
- **Order the inbox after the effect.** A workflow start cannot share the
  database transaction. Start with the deterministic workflow ID, treat
  "already started" as success, then record the inbox. A crash before the inbox
  write repeats an idempotent effect; it does not lose the command.
- **Effect tokens** go into sandbox calls, egress writes, payments, and message
  sends. The receiving side dedupes on the token, not on our retries.
- **Kafka offsets** commit only after the effect or the inbox row commits. An
  unhandled error stops the consumer before it commits, so the bus redelivers.
  Duplicates are safe; lost events are not.
- **Approvals are single-use** with an expiry; a replayed approval event must not
  release a second send. The approval row is the claim: it changes only from
  `pending`, and a repeat of the stored decision may signal again.

## 6. Ordering, priority, fairness

- **Partition by `org_id`** and require order only within a conversation.
  Cross-conversation ordering is explicitly not guaranteed.
- **Priority classes** live in the envelope so the sender decides, not the
  consumer: `interactive` outranks `routine` outranks `backfill`. Kafka has no
  message priority, so use one topic per class or filter in the consumer.
- **Preemption:** an interactive message to a busy conversation does not queue
  behind the run. Signal the active run to yield at its next step; if it does not
  yield within a grace window, cancel it and start the interactive run. Bounded
  cancellation, not a hard kill.
- **Fairness:** per-org concurrency quotas on the harness task queue, plus a cap
  on active runs per org. One tenant's backfill must never starve another
  tenant's chat. Measure queue wait p99 per class, not just average latency.
- **Batching:** drain the signal queue for a quiet window of a few seconds before
  starting a turn. Three quick messages become one turn.

## 7. Waiting without polling

Runs wait on other services (document indexed, backfill complete, retrieval
ready). Temporal has no index of "who is waiting for X", so maintain one:

1. The workflow registers a waiter row: `(subject, run_id, workflow_id, deadline)`.
2. The consumer, on the awaited event, looks up waiters by subject and signals
   each workflow.
3. **Race:** the event may arrive before the waiter registers. The consumer
   records the event in a per-subject `pending` table; the workflow, after
   registering, re-checks `pending` inside a `wait_condition`. Register then
   re-check closes the gap.
4. Always set a deadline. A wait without a timeout is an outage waiting to
   happen; on expiry, mark the dependency degraded and let the run finish with a
   caveat.

## 8. Memory: episodic owned, organisational called

| Layer | Lives in | Owner | Read when |
|---|---|---|---|
| Core facts | Profile file, in every prompt | This service | Every turn |
| Dated logs | Files in the sandbox | This service | Searched on demand |
| Scratchpad | Files, ephemeral | This service | This hour, then discarded |
| Skills | Markdown files | This service | On demand |
| Org knowledge | HelixDB graph and vectors | Ingestion | Via `retrieve`, lazily |

HelixDB specifics:

- Isolation is either a `tenant_id` property on every node and edge, or a
  separate database per tenant. Both are supported; the first is the default,
  the second is the regulated tier.
- Every query must include the tenant filter. Build the filter in one helper and
  do not let callers write it. Isolation that depends on every author remembering
  is not isolation.
- Enable tenant-partitioned vector and text indexes so one tenant's search does
  not warm the caches of another.
- Tenants share compute. Rate-limit the retrieval service per tenant.

Retrieval results are written to a file and the **path** is returned to context,
not the document body. Retrieved text is untrusted input and is never treated as
an instruction.

## 9. Observability

- Propagate `traceparent` from the envelope into Temporal via interceptors and
  activity headers, so one trace spans channel, bus, workflow, tool, and sandbox.
- Span attributes: `org_id`, `conversation_id`, `run_id`, `step_index`,
  `tool_name`, `model`, `cache_hit`, `tokens_in` and `tokens_out`.
- Cost attribution happens at the LLM gateway, keyed by `org_id`; do not
  reconstruct billing from logs.
- Log JSON with IDs, not prose. Log prompt hashes and object-store references by
  default; full prompts only behind a flag, with retention limits and no secrets.
- Per-stamp dashboards for dedicated deployments, plus one fleet view of version,
  lag, and error rate per stamp.
- The four numbers that matter: run success rate, p99 turn latency, cache hit
  ratio, consumer lag.

## 10. Versioning and evolution

The talk's "delete the product" applies to the harness, not to the contracts.

- **Event schemas:** version per type, additive-only, registry checked in CI,
  contract tests on both producer and consumer. Removing or retyping a field is a
  new event type.
- **Workflows:** keep them thin and version them. Enable Temporal worker
  versioning (build IDs) where the SDK supports it; otherwise pin workers, drain,
  and deploy. `continue-as-new` before the history limit (about 51k events or
  50 MB by default) for multi-day runs.
- **Activities:** freely editable; they are not replayed. This is where the
  harness lives, precisely so it can churn monthly.
- **Fleet:** define a supported-version window. A dedicated stamp may lag by one
  minor version, never two. Migrations must be expand and contract, because old
  and new versions run at the same time during a rollout.
- **Migrations:** the same rule for the product database and for event payloads.
  Both are read by services you do not deploy.

## 11. Tenancy and isolation

`org_id` is the only tenant key. It is in the token, the envelope, every row,
every log line, every workflow ID, and every HelixDB record.

- **Derive it at the edge** from the identity token. Never accept a tenant ID
  from a request header or payload.
- **Identity:** an OIDC provider (Zitadel or Keycloak) issues the token. Services
  validate the signature through JWKS and read `sub`, `org_id`, `roles`, and
  `scopes`. No service stores passwords.
- **Propagation:** the edge signs the tenant context and passes it in gRPC
  metadata. Services trust only the edge, never the client.
- **Postgres:** shared schema with `org_id` and row-level security, or schema per
  tenant, or database per tenant. The profile decides; the code does not.
- **HelixDB:** `tenant_id` property with an equality index, or a database per
  tenant for the regulated tier.
- **Temporal:** in a shared cell, one namespace per bounded context (or per
  residency tier), never per tenant. In a dedicated stamp, namespaces may be
  scoped to the stamp. Put `org_id` in the workflow ID and in search attributes.
- **Kafka:** partition by `org_id`; apply per-tenant consumer quotas.
- **Test:** a tenant that forges another `org_id` must get a 403 or an empty
  result, never another tenant's data. Run a cross-tenant leak test in CI.

## 12. Failure modes

| Failure | Behaviour | Mitigation |
|---|---|---|
| Consumer crashes mid-effect | Event redelivered | Inbox uniqueness, effect token |
| Workflow waits on approval forever | Run parked | Deadline, then deny and notify |
| Identity provider unavailable | New logins fail, tokens expire | Cache JWKS, long token lifetime, status page |
| Kafka unavailable | Events queue at producers, turns delay | Producer buffer, alert on lag, no data loss at the DB |
| Retrieval or HelixDB down | Tool returns degraded result | Run proceeds, or waits with a deadline |
| Sandbox dies mid-run | Activity fails | Re-provision from snapshot, retry with token |
| LLM gateway 429 or 5xx | Activity retries | Retry policy plus concurrency cap |
| Poison event | Retries exhaust | Dead-letter topic, alert, run marked failed |
| Workflow fails terminally | Temporal has no dead-letter queue | `agent.run.failed` is the dead letter: alert, keep history |
| Stamp upgrade fails | One customer degraded | Canary per stamp, rollback image, version pin |
| Clock skew on deadlines | Early or late expiry | Server time only, generous jitter |

## 13. Anti-patterns

- A cross-service saga built from events.
- A second orchestrator: bus-driven retries alongside Temporal.
- Workflow IDs, signals, or queries leaking into an external API.
- Other services querying Temporal for status.
- Polling instead of a signal plus a subscription table.
- Eagerly stuffing retrieved org knowledge into the prompt prefix.
- An event per tool call.
- Claiming exactly-once instead of making effects idempotent.
- Unbounded retries with no dead-letter and no owner.
- A fork or a branch per customer.
- One Temporal namespace per tenant.
- Trusting a tenant ID that arrived from a client.
- Linking a database SDK into the harness.

## 14. Dependencies

No sequence and no schedule; these are the things that must exist for each
service to function.

- **Platform prerequisites for everything:** Temporal, Postgres, object storage,
  Kafka, schema registry, identity provider, observability pipeline.
- **Agent service:** Temporal, Postgres, object store, Kafka, retrieval, sandbox,
  secret broker, LLM gateway.
- **Sandbox:** KVM hosts, object store for snapshots, secret broker.
- **Retrieval:** HelixDB, identity provider.
- **Ingestion:** HelixDB, object store, Kafka, a scheduler.
- **Channels:** identity provider, Kafka, provider APIs.
- **Approvals:** Postgres, Kafka, identity provider, channels.
- **Evals:** event archive, harness activities, object store.

## 15. Open questions

- Who owns message rendering and delivery — this service or channels?
- Who owns the retrieval service — this team or the ingestion team?
- Per-tenant namespaces versus shared namespaces, now that dedicated stamps
  exist: cost against blast radius.
- Data residency for org knowledge and for agent memory: same region or not.
- BYOC packaging: Helm chart only, or an operator that the customer runs?
- Approval SLA per action class, and what "expired" means for money movement.
- Whether `agent.observation.recorded` should feed ingestion, and under whose
  schema.

## References

- [ACHITECTURE.md](ACHITECTURE.md) — the source talk, sections 01–06.
- [BUILD.md](BUILD.md) — the full service inventory and definitions of done.
- [reference/architecture-map.html](../reference/architecture-map.html) — the
  one-page map of the product.
- [LANGUAGE.md](LANGUAGE.md) — what is Rust and what is Python, and why.
- [RESOURCES.md](../course/RESOURCES.md) — Temporal, 12-Factor Agents, Firecracker,
  context engineering.
- [HelixDB multi-tenancy](https://docs.helix-db.com/database/helix-cloud/operate/multi-tenancy)
  and [deployment options](https://docs.helix-db.com/database/helix-db/start-here/run-modes).
- [Kafka documentation](https://kafka.apache.org/documentation/) and
  [Redpanda](https://docs.redpanda.com/) for the Kafka-compatible broker.
- [Zitadel](https://zitadel.com/docs) and [Keycloak](https://www.keycloak.org/documentation)
  for the identity provider.
