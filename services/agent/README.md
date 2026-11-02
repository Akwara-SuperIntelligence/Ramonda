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

## Coverage

Every increment names its sources. This table is the running index.

| Source | Where it lives here | Delta |
|---|---|---|
| talk §03 — durable workflow, resume at the failed step | `src/agent_service/workflow.py` | Temporal replaces the hand-rolled journal |
| talk §04 — the harness executes tool calls | `src/agent_service/activities.py` | The model is an activity, not a workflow line |
| lesson 01 — a turn is three steps, repeated | `workflow.py`, `tests/test_run.py` | The steps are activities |
| lesson 02 — write the intent down first | `workflow.py` | The event history is the journal |
| lesson 03 — the process is not the agent | `worker.py`, `cli.py` | A worker replaces the threaded HTTP server |
| EDA §5 — every effect carries a token | `activities.py` | Marker file is the effect; a repeat is a no-op |

## Verified

A worker was killed with `SIGKILL` while 108 turns were in flight. A new worker
completed all 200, with no duplicate or lost turn.

A duplicate effect token writes nothing, and a marker is only linked into place
after its content is complete, so a crash cannot leave half an effect.

## Setup

The venv lives at the repository root and uses Python 3.12.

```
../../.venv/bin/pip install -e ".[dev]"    # from this directory, once
```

## Run

```
../../.venv/bin/python -m pytest           # from this directory
```

To run a real turn, a Temporal server is needed:

```
temporal server start-dev                   # terminal 1
../../.venv/bin/python -m agent_service.worker      # terminal 2
../../.venv/bin/python -m agent_service.cli "hello" # terminal 3
```

The worker and CLI read `TEMPORAL_ADDRESS`, default `localhost:7233`.
