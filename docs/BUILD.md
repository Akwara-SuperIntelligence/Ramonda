# BUILD: the full system

This is the service inventory for the production system. Each entry describes the
**finished service**: what it is for, how it is reached, what it owns, what it
needs, what it does when something breaks, and what "done" means.

It contains no phases, no durations, and no roadmap. Ordering appears only as
dependency: if a service needs another, the dependency is stated.

Where this document and [EDA.md](EDA.md) disagree, EDA.md wins for the agent
service; this document wins for the inventory. Language choices follow
[LANGUAGE.md](LANGUAGE.md).

## 1. System map

```
        clients: web, mobile, terminal, Slack, email
                            │
                       edge gateway
                            │
      ┌─────────────────────┼──────────────────────┐
      │                     │                      │
  agent service        approvals service      admin console
      │  (Temporal)          │
      │                      │
      ├── retrieval ──▶ HelixDB ◀── ingestion ◀── connectors
      ├── sandbox platform (Rust)
      ├── secret broker and egress proxy
      └── LLM gateway
                            │
      Kafka ◀── outbox ─────┘        all services ──▶ telemetry
```

## 2. Inventory

| Service | Owner | Language | State | Criticality |
|---|---|---|---|---|
| Edge gateway | Us | Rust | Stateless | Critical |
| Agent service | Us | Python | Temporal, Postgres | Critical |
| Sandbox platform | Us | Rust | Hosts, object store | High |
| Retrieval service | Us or ingestion team | Python | Read-only | High |
| Ingestion pipeline | Ingestion team | Their call | HelixDB, object store | High |
| Channels and delivery | Us | Python | Provider state | Medium |
| Approvals service | Us | Python and OPA | Postgres | High |
| Secret broker and egress proxy | Us, or adopt Vault | Rust | Encrypted secrets | Critical |
| LLM gateway | Us, or adopt | Go or Python | Usage ledger | High |
| Evals service | Us | Python | Eval cases, results | Medium |
| Admin console | Us | TypeScript | Tenant config | Low |

Adopted, not built: Temporal, Kafka (Redpanda or managed), Apicurio schema
registry, Postgres, object storage, an OIDC identity provider (Zitadel or
Keycloak), OpenTelemetry, Kubernetes, KMS.

## 3. Cross-cutting definition of done

Every service we build must satisfy all of these, in addition to its own entry.

- **Identity.** Validates tokens from the identity provider. Derives `org_id`
  from the token. Never accepts a tenant ID from a request.
- **Tenant isolation.** Every read and write is scoped by `org_id`. A cross-tenant
  leak test runs in CI.
- **Contracts.** Consumes and produces versioned events through the schema
  registry. Additive changes only. Contract tests on both sides.
- **Idempotency.** Every externally caused effect has an idempotency key. Replay
  is safe.
- **Tracing.** Propagates `traceparent`. Emits spans with `org_id` and, where
  relevant, `run_id`.
- **Logging.** Structured JSON with IDs, never prose. No secrets, no full prompts
  by default.
- **Health.** Liveness and readiness endpoints. A dependency failure degrades; it
  does not crashloop.
- **SLOs.** Latency and error SLOs recorded, with one alert per SLO.
- **Migrations.** Expand and contract. Old and new versions run at once during a
  rollout.
- **Deployment.** One container image per service, immutable tag, SBOM, no
  `latest`. Runs in all three deployment profiles.
- **Secrets.** Fetched from the secret broker at runtime. No secrets in images,
  environment files, or logs.
- **Runbook.** Each alert names one action. Each service has a restore drill.
- **Ownership.** One team on call, one repository, one deploy pipeline.

## 4. Contracts

- **Identity token.** JWT from the identity provider. Claims: `sub`, `org_id`,
  `roles`, `scopes`, `exp`. Verified through JWKS with rotation.
- **Internal context.** The edge signs `{org_id, user_id, scopes, traceparent}`
  and passes it as gRPC metadata. Services trust only the edge.
- **Events.** Envelope and naming in [EDA.md](EDA.md) §4.1. `event_id` is never
  reused. Unknown fields and unknown types are tolerated.
- **Commands.** Idempotent on `command_id`. Reply event on success or failure.
- **Tool surface.** Names and JSON schemas are owned by the agent service
  (`run_shell`, `send_user`, `remember`, `recall`, `delegate`, `retrieve`,
  `browser`). Changing a schema is a versioned change.
- **Errors.** Every error carries `code`, `retryable`, and `degraded` flags.
  Callers must not infer retry behaviour from message text.
- **Identifiers.** ULIDs for events and commands. Workflow ID
  `turn:{event_id}`. Sandbox ID `sbx:{org_id}:{ulid}`.
- **Versioning.** Semantic versions for APIs, integer versions for events,
  immutable image tags for deployments.

## 5. Data ownership

One writer per store. Readers go through the owning service, not the store.

| Store | Owner | Writers | Readers |
|---|---|---|---|
| Postgres, agent | Agent service | Agent service only | Agent service, evals via API |
| Postgres, approvals | Approvals service | Approvals service | Approvals service, audit |
| HelixDB | Ingestion pipeline | Ingestion only | Retrieval service |
| Object store, artifacts | Agent service | Agent service | Evals, admin |
| Object store, snapshots | Sandbox platform | Sandbox only | Sandbox only |
| Object store, raw documents | Ingestion pipeline | Ingestion only | Ingestion, retrieval |
| Kafka | Platform | Producers | Consumers |
| Temporal persistence | Temporal | Temporal | Temporal |
| Identity database | Identity provider | Identity provider | Identity provider |

Kafka is transport, not a system of record. If it must be replayed from the
beginning, the archive in object storage is the source.

## 6. Services we build

### 6.1 Edge gateway

**Purpose.** The single entry for clients. Authenticates, resolves tenant
context, rate-limits, routes, and streams replies.

**Interface.** Inbound HTTPS, WebSocket, and SSE from clients. Outbound gRPC to
the agent and approvals services, plus events to Kafka.

**Owns.** Session and connection state only. No business data, no database of
record.

**Depends on.** Identity provider, agent service, approvals service, Kafka,
schema registry.

**Language.** Rust. It terminates every client connection, so it is the one
service where connection count, not model latency, sets the cost.

**Failure.** Rejects with 503 rather than serving partial context. Streams resume
with `Last-Event-ID`.

**Done when:**
- JWTs are validated, unknown issuers rejected, JWKS cached with rotation.
- `org_id` comes from the token; client-supplied tenant headers are stripped.
- Internal context is signed; trace context is propagated.
- Rate limits apply per org and per user.
- Slow clients get backpressure, never unbounded buffering.

### 6.2 Agent service

**Purpose.** The always-on agent. Consumes commands and events, runs one durable
workflow per turn, calls the harness, keeps episodic memory, and gates
irreversible actions.

**Interface.** Commands over HTTP or gRPC. Events in from Kafka. Events out
through the outbox. gRPC to sandbox, retrieval, secret broker, LLM gateway, and
channels.

**Owns.** Conversations and their transcripts, episodic memory, inbox and outbox, pending
approvals, the run index.

**Depends on.** Temporal, Postgres, object storage, Kafka, retrieval, sandbox,
secret broker, LLM gateway, identity provider.

**Language.** Python.

**Failure.** Workflow retries resume at the failed step. Terminal failure emits
`agent.run.failed` and keeps the history. Consumer lag delays turns; it does not
lose them.

**Done when:**
- A killed worker resumes the turn at the failed step.
- Duplicate events are absorbed by the inbox; duplicate starts by the workflow ID.
- Every side effect carries an effect token.
- Long tool output goes to object storage; the context gets a path.
- The prompt prefix is stable; cache hit ratio is measured per model.
- Memory layers behave: core facts every turn, dated logs searched, scratchpad
  discarded, skills read on demand.
- Compaction runs inside the warm cache window and is measured.
- Sub-agents run as child workflows on their own task queue.
- Irreversible tools stop at an approval gate with a deadline.
- Silence is a policy decision, not a model decision.
- Per-org quotas and priority classes are enforced.
- Traces span channel, bus, workflow, tool, and sandbox.
- Every run is replayable from its history for evals.

### 6.3 Sandbox platform

**Purpose.** Disposable Linux computers for agents: create, execute, snapshot,
restore, destroy, and browser control where enabled.

The first version covers create, exec, file operations, snapshot, restore, and
destroy. Browser and desktop control come after egress and the secret broker.
Recording a session to learn a skill is not in the first version.

**Interface.** gRPC control API for create, exec, file operations, snapshot,
restore, and destroy. vsock to the in-guest agent. WebSocket screen stream.

**Owns.** VM metadata, golden images, snapshots in object storage, host capacity.

**Depends on.** KVM hosts, object storage, secret broker, identity provider.

**Language.** Rust.

**Failure.** A lost VM is re-provisioned from a golden image. A corrupt snapshot
fails the run with a reason. A bad host is drained.

**Done when:**
- Per-org quotas and a TTL reaper exist.
- Snapshot and restore are tested end to end.
- CPU, memory, disk, and process limits are enforced.
- Seccomp and no-new-privileges are on; egress is denied by default.
- Credentials arrive as short-lived leases, never in the guest image.
- Escape attempts in the test suite fail.
- Every action is audited with `org_id` and `run_id`.

### 6.4 Retrieval service

**Purpose.** The only read path to organisational knowledge. Tenant-scoped
search over the graph and vectors, with provenance.

**Interface.** HTTP or gRPC query returning compact results plus citations.
Authenticated by internal context.

**Owns.** No persistent data. Read-only over HelixDB.

**Depends on.** HelixDB, identity provider.

**Language.** Python.

**Failure.** Returns a degraded result with a reason and a timeout, never a hang.

**Done when:**
- The tenant filter is built in one place and cannot be bypassed.
- Tenant-partitioned vector and text indexes are used.
- Results are capped in size; documents are referenced, not inlined.
- Per-tenant rate limits protect shared compute.
- Every result carries a source and a score.

### 6.5 Ingestion pipeline

**Purpose.** Connect sources, parse, chunk, embed, and write the organisational
graph. Emit indexing events.

**Interface.** Consumes source events. Writes HelixDB and object storage. Emits
`ingestion.document.indexed` and failure events.

**Owns.** Raw documents, ingestion state, the graph write path.

**Depends on.** HelixDB, object storage, Kafka, scheduler, embedding model, source
APIs.

**Language.** The owning team's call; Rust for heavy parsers if needed.

**Failure.** Per-document retries, then a dead-letter topic. One bad document
never blocks a batch.

**Done when:**
- Documents are deduplicated by content hash.
- Writes are idempotent and tenant-scoped.
- Backfill and incremental sync both work.
- Delete and forget requests remove nodes, edges, and vectors.
- Provenance is stored for every chunk.
- Indexing completion is published for waiting runs.

### 6.6 Channels and delivery

**Purpose.** Turn `agent.message.composed` into a Slack message, email, or push
notification, and turn inbound messages into `SendMessage` commands.

**Interface.** Kafka in and out, plus provider APIs.

**Owns.** Delivery state and provider credentials.

**Depends on.** Identity provider, Kafka, provider APIs.

**Language.** Python.

**Failure.** Retries with backoff, then a dead-letter topic and a user-visible
failure event.

**Done when:**
- Sending is idempotent per message ID.
- Approval cards render and resolve.
- Threads and replies map to the right conversation.
- Per-provider rate limits are respected.
- No rendering or product policy lives in the agent service.

### 6.7 Approvals service

**Purpose.** Durable approval requests for irreversible actions, with expiry,
single use, and audit.

**Interface.** Consumes `agent.approval.requested`. Emits
`agent.approval.resolved`. Exposes a UI and `ResolveApproval`.

**Owns.** The approvals table and policy decisions.

**Depends on.** Postgres, Kafka, identity provider, channels.

**Language.** Python, with OPA or Cedar for policy.

**Failure.** Expiry denies. A second resolve is rejected.

**Done when:**
- Approval tokens are single-use and expire.
- Every request names the action, the payload, and the consequences.
- Policy is evaluated per tenant and per action class.
- The full trail is auditable.

### 6.8 Secret broker and egress proxy

**Purpose.** Keep credentials out of model context and sandboxes. Inject
short-lived credentials and restrict egress.

**Interface.** gRPC lease requests from the sandbox and agent. Egress proxy with
an allowlist.

**Owns.** Encrypted secrets, leases, the egress policy.

**Depends on.** KMS, identity provider, audit log.

**Language.** Rust, or adopt Vault or OpenBao.

**Failure.** Fails closed. No lease, no call.

**Done when:**
- Leases are short-lived and scoped to one tenant and one purpose.
- Credentials never appear in logs, context, or images.
- Egress is denied by default and allowed by rule.
- Rotation is automated and audited.

### 6.9 LLM gateway

**Purpose.** One egress to model providers. Keys, retries, quotas, cost
attribution, and cache metrics.

**Interface.** OpenAI-compatible HTTP. Usage events to Kafka.

**Owns.** Provider keys and the usage ledger.

**Depends on.** Model providers, Kafka, identity provider.

**Language.** Adopt a product, or Go or Python if built.

**Failure.** Passes 429 and 5xx with retry hints. Fails over between providers
where configured.

**Done when:**
- Per-org quotas and model allowlists are enforced.
- Every request emits cost and token counts tagged with `org_id`.
- Prompt cache hits and misses are recorded.
- Provider keys never leave the gateway.

### 6.10 Evals service

**Purpose.** Turn real failures into eval cases, run suites, and gate releases.

**Interface.** Consumes run events, reads the archive, writes results. Runs in CI
and on demand.

**Owns.** Eval cases and results.

**Depends on.** Object storage, harness activities or a replay runner, Postgres.

**Language.** Python.

**Failure.** A failed eval run alerts. It never takes production down.

**Done when:**
- Every case traces to a real run.
- Assertions are deterministic; no model-as-judge without a recorded baseline.
- Regressions block a release.
- Scores are per capability, not one aggregate number.

### 6.11 Admin console

**Purpose.** Back-office for tenants, quotas, feature flags, stamp inventory, and
audit.

**Interface.** HTTP UI and API.

**Owns.** Tenant configuration.

**Depends on.** Identity provider, Postgres, agent service read API.

**Language.** TypeScript.

**Failure.** Degrades to read-only; never blocks agent traffic.

**Done when:**
- Tenant create, suspend, and quota change are audited.
- Feature flags are per tenant and per stamp.
- The fleet view lists every stamp, its version, and its lag.
- Support can see a run without seeing secrets.

## 7. Platform we adopt

| Component | What we must configure |
|---|---|
| Temporal | One cluster; namespace per bounded context or residency tier; retention; archival; worker versioning; alerting on task backlog |
| Kafka | Topics per event family and priority class; partition key `org_id`; dead-letter topics; retention; per-tenant quotas |
| Schema registry | Compatibility mode; CI check; one subject per event type |
| Postgres | One database per service; row-level security where shared; backup and restore drill |
| Object storage | Cloudflare R2 by default; versioning; lifecycle; per-stamp buckets; encryption with customer keys in BYOC. See [ADR 0007](adr/0007-r2-provider.md) |
| Identity provider | Realms or organisations per stamp; OIDC clients per service; JWKS rotation |
| OpenTelemetry | One collector per stamp; trace sampling policy; redaction rules |
| Kubernetes and Helm | One chart per service; values per profile; canary per stamp |
| KVM hosts | Dedicated node pool for the sandbox; capacity headroom; drain procedure |
| KMS | Per-stamp keys; BYOK where required |

## 8. Deployment profiles

The same artifacts run in all three. Only the values change.

| Concern | Shared cell | Dedicated stamp | BYOC |
|---|---|---|---|
| Tenant model | Many per deployment | One per deployment | One per deployment |
| Postgres | Shared, row-level security | Dedicated instance | Customer-managed |
| HelixDB | Shared database, `tenant_id` | Dedicated database or cluster | Customer-managed |
| Temporal | Shared cluster, namespace per context | Namespaces scoped to the stamp | Customer-managed or ours |
| Kafka | Shared cluster, topic per class | Shared or dedicated | Customer-managed |
| Object storage | Shared bucket, prefixed | Dedicated bucket | Customer bucket |
| Keys | Our KMS | Our KMS, per stamp | Customer KMS |
| Sandbox | Shared host pool | Dedicated pool | Customer hosts |
| Idle stop | Consumer on Kafka lag, small warm worker pool | Same, one stamp | Customer sets minimum replicas |
| Upgrades | Continuous | Canary per stamp | Customer applies a release |

### Idle stop

The agent worker and consumer are long-running processes. They poll Temporal and
Kafka, so an idle deployment still pays for them. "Stops after two idle minutes"
is a deployment property, not a line in the workflow.

- **Shared cell.** Scale the consumer on Kafka lag (KEDA or equivalent). Scale
  the Temporal worker on task backlog, or keep a small warm pool. Full
  scale-to-zero is allowed, but a cold start delays the first turn.
- **Dedicated stamp.** Same mechanics, one deployment per customer. Keep a warm
  minimum if the customer expects instant replies.
- **BYOC.** The customer chooses. We ship the chart and the metrics; the values
  decide the minimum replicas.
- **Not the sandbox.** A sandbox VM can stop independently (see §6.3). That is a
  different idle stop from the agent process.

Current state: neither process stops when idle. The metric that would drive the
decision is the consumer lag in [ADR 0004](adr/0004-metrics-quotas.md); the
autoscaling policy is a deployment decision, not application code.

## 9. Dependencies

- **Everything:** Temporal, Postgres, object storage, Kafka, schema registry,
  identity provider, telemetry, KMS.
- **Agent service:** retrieval, sandbox, secret broker, LLM gateway, channels.
- **Sandbox:** KVM hosts, object storage, secret broker.
- **Retrieval:** HelixDB.
- **Ingestion:** HelixDB, object storage, scheduler, source APIs.
- **Channels:** provider APIs.
- **Approvals:** channels, policy engine.
- **Evals:** event archive, agent activities.
- **Admin:** agent read API, tenant store.

## 10. Out of scope for this document

Billing and metering, the analytics warehouse, native mobile clients, model
training and fine-tuning, the marketing site, and the ingestion team's internal
design. They exist; they are not specified here.

## 11. Open decisions

- Owner of the retrieval service: this team or the ingestion team?
- Owner of channels and delivery: shared platform or this product?
- Identity provider: Zitadel or Keycloak?
- BYOC packaging: Helm chart only, or an operator the customer runs?
- Whether the edge gateway lives in this repository or its own.
- What the analytics and evals archive from the retained rows (the agent service
  retention windows are set in [ADR 0003](adr/0003-retention-deletion-health.md)).
- Whether the evals service reads the agent database or only the event archive.
