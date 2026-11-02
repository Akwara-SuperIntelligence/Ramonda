# services/agent

The agent service. Python. One deployable: consumer, orchestrator, harness.

## Rules

- **Workflows are thin and deterministic.** No I/O, no clock, no randomness in
  workflow code. All of it lives in activities.
- **Every activity is idempotent.** Key it by `workflow_id` and step, and pass an
  effect token to every side effect.
- **Tenant context comes from the edge.** Never read `org_id` from a payload or a
  header the client controls.
- **The harness never links a database SDK.** Call the retrieval API. Call the
  sandbox over gRPC. Call the secret broker. Never connect to the graph store.
- **Long output goes to object storage.** The context gets a path, not a blob.
- **The prompt prefix stays stable.** A cache miss is a bug.
- **`course/` is not imported, copied, or cited in code.** It is reference only.

## Contracts

- Events: [docs/EDA.md](../../docs/EDA.md) §4.1
- Commands and tools: §4.3 and §4.4
- Workflow IDs: `run:{conversation_id}:{seq}`

## Commands

To be added with the first code. Until then, there is nothing to build or run.

## Definition of done

[docs/BUILD.md](../../docs/BUILD.md) §6.2, plus the cross-cutting list in §3.
