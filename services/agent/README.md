# services/agent

The agent service: one deployable that hosts the event consumer, the Temporal
orchestrator, and the harness worker. Python.

## Status

No code yet. This directory is where [docs/EDA.md](../../docs/EDA.md) becomes
software.

## Read first

- [docs/EDA.md](../../docs/EDA.md) — the service design
- [docs/BUILD.md](../../docs/BUILD.md) §6.2 — the definition of done
- [docs/LANGUAGE.md](../../docs/LANGUAGE.md) — why Python
- [AGENTS.md](AGENTS.md) — rules for working in this directory

## Boundary

Owns conversations, episodic memory, run orchestration, approval policy, and
evals over its own traces.

Calls retrieval, the sandbox, the secret broker, the LLM gateway, channels, and
the identity provider.

Does not own the bus, the graph store, the sandbox, or the identity provider.

## Target layout

```
src/agent_service/
  consumer/     inbox, dedupe, envelope handling
  workflows/    thin, deterministic, versioned
  activities/   harness: model, context, tools, memory
  tools/        run_shell, send_user, remember, recall, delegate, retrieve, browser
tests/
migrations/
Dockerfile
```
