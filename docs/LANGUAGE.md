# Language split: Rust and Python

Scope: **this service** (the always-on agent) and the platform services it calls.
The architecture is in [EDA.md](EDA.md); the full inventory is in
[BUILD.md](BUILD.md); the product is in [ACHITECTURE.md](ACHITECTURE.md).

Supersedes earlier drafts of this split: the durable-execution engine is not ours
(Temporal), and the edge gateway, LLM gateway, sandbox, identity, and retrieval
are separate services rather than sidecars.

## The rule

Language follows **rate of change × blast radius**, not performance.

- **Python decides, Rust delivers.** Anything encoding product judgement or model
  behaviour is Python. Anything that is a transport, a supervisor, or a security
  boundary is Rust.
- **The boundary is the network.** gRPC or HTTP between services; no FFI and no
  PyO3 unless a profiler demands it.
- **Rust must earn its place.** Every additional language is another build,
  deploy, and debug surface — and the product is designed to be rewritten every
  model generation. Keep the Rust surface small and boring.

## Constraints that fix the split

1. **Temporal has no official Rust SDK** (Go, Java, TS, Python, .NET, PHP, Ruby).
   Rust cannot be a workflow worker; it stays outside the workflow layer
   entirely. This is the biggest single determinant of the split.
2. **Workflow code is the least changeable thing you own** (determinism,
   versioning, replay). The harness is the most changeable. So the harness lives
   in activities — where it can churn freely — and never in the workflow.
3. **The loop is I/O-bound.** A model call is seconds; JSON is microseconds. Rust
   buys nothing on the hot path of the agent loop.
4. **The sandbox is kernel-adjacent and a security boundary.** Memory safety,
   async I/O, static binaries, no GIL, precise limits. That is where Rust pays.
5. **Ecosystem gravity.** Model SDKs, tokenizers, eval tooling, Slack and IMAP
   clients are Python-first. Fighting that is a tax with no payoff.
6. **BYOC raises the bar on artifacts, not on language.** A customer-run
   deployment needs self-contained images: pinned wheels, no runtime downloads,
   no build step at install. Rust static binaries help; Python is fine inside a
   well-built container.
7. **Polyglot tax.** Every Rust service is one more thing to operate. Two
   languages is the ceiling for a small team.

## This service

| Component | Language | Why | Revisit if |
|---|---|---|---|
| Workflows (orchestrator) | Python | Must be the SDK language; thin, versioned | Never (SDK constraint) |
| Harness activities: model calls, context assembly, compaction, tool dispatch | Python | Changes monthly; SDK and eval ecosystem | A single activity becomes CPU-bound |
| Bus consumer and ingress | Python | Mostly I/O, validation, dedupe | Sustained fan-in where per-event CPU dominates |
| Tool policy (allow and deny, auto-review, redaction) | Python | Model calls and judgement | Almost never |
| Memory policy, retrieval ladder, compaction algorithm | Python | Product behaviour | If tokenisation or diffing dominates |
| Outbox relay | Python, or CDC (Debezium) | Boring glue; do not hand-roll correctness | Throughput outgrows a poller |
| Retrieval client (HTTP to the retrieval service) | Python | Thin client, no local schema | Never |
| Event schemas | Neutral artefact (JSON Schema or Protobuf) | Contract, not code | Never |
| Evals | Python | pytest, datasets; if it is not Python you will not run it | Never |

## Services we call, not own

| Service | Language | Note |
|---|---|---|
| Sandbox control plane and in-guest agent | **Rust** | Firecracker lifecycle, snapshots, vsock, exec, CDP |
| Secret broker and egress proxy | **Rust**, or adopt Vault or OpenBao | Must sit outside the model's reach |
| LLM gateway | Not ours | Rate limits, key rotation, cost attribution per org |
| Channels and delivery | Python if ours; otherwise the owner's call | Ownership is an open decision, see EDA §15 |
| Retrieval and ingestion | Ingestion team's call | HelixDB is Rust; the agent sees only the retrieval HTTP API |
| Identity provider | **Adopt**: Zitadel (Go) or Keycloak (Java) | Never build this |
| Kafka or Redpanda | **Adopt** | Protocol choice, not code we write |
| Schema registry | **Adopt**: Apicurio | Contract storage |

## Edge gateway

Rust, decided. It terminates every client connection and resolves tenant context
before any product service sees the request. It is stateless, so it ships and
scales on its own. See [BUILD.md](BUILD.md) §6.1.

## Rust, ranked by when it pays

1. **Sandbox control plane and guest agent** — pays at the first additional
   tenant or the first snapshot requirement. `axum`, `tokio`, `tonic`,
   Firecracker's unix-socket HTTP API, `tokio-vsock`, `seccompiler`,
   `chromiumoxide` for CDP.
2. **Edge gateway** — decided Rust. Long-lived client connections, streaming, and
   tenant resolution at the door.
3. **Secret broker and egress proxy** — pays at the first real credential.
4. **Accessibility-tree extraction and pruning in the guest** — pays when browser
   control becomes core, because it turns screenshots into cheap diffs.

Everything else stays Python. Not because Rust could not do it, but because it
changes weekly and the latency belongs to the model.

## Anti-rules

- No Rust Temporal worker.
- No loop control flow in Rust.
- No evals in Rust.
- No PyO3 on the loop's hot path and no FFI across the workflow boundary.
- No second vector index inside this service.
- No HelixDB or any database SDK linked into the agent service; call the
  retrieval API.
- No rewriting the Python consumer in Rust before consumer lag is measured.

## What changed from earlier drafts

| Row | Before | Now |
|---|---|---|
| Durable execution engine | Rust if built | Bought: Temporal (Go server) |
| Edge gateway | Rust only if measured | Rust, decided |
| LLM gateway | Rust row | Platform service, not ours |
| Sandbox | Rust sidecar | Rust **platform** service |
| Bus consumer | Absent | Python here; Rust only on measured pressure |
| Bus | Not specified | Kafka protocol; adopted broker |
| Knowledge store | Not specified | HelixDB, behind retrieval; not linked into the agent |
| Identity | Not specified | Adopted OIDC provider; never ours |
| Deployment | Shared by default | Three profiles over one artifact set |

The internals are unchanged: Python harness, thin workflows, thick activities,
idempotent effects, evals from real failures.

## For the capstone

The course build stays **Python only** — a local Temporal server, one worker, one
sandbox directory. Rust enters at the one point the capstone outgrows "a
directory with `subprocess`", and even then the honest move is to adopt a sandbox
rather than write the supervisor.

## Signals to revisit

Rust should get more surface only when one of these is measured, not predicted:
p99 latency dominated by our own code, memory per idle connection, a supervisor
that leaks over days, a security boundary where a bug is an RCE, or consumer lag
that survives scaling Python workers.
