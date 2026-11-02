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
| EDA §5 — every effect carries a token | `activities.py`, `migrations/001_init.sql` | The effects table is the claim; a repeat is a no-op |
| talk §05 — memory lives outside the context window | `activities.py` (`load_history`, `save_turn`) | History is read from Postgres, not carried in the input |
| lesson 07 — memory is stored so it can be recalled | `workflow.py`, `migrations/001_init.sql` | A turn is appended once, keyed by `(conversation, seq)` |
| talk §02 — the model chooses, the harness executes | `activities.py` | Real DeepSeek call replaces the scripted reply |

## Verified

A worker was killed with `SIGKILL` while 108 turns were in flight. A new worker
completed all 200, with no duplicate or lost turn.

A duplicate effect token writes nothing, and a turn is saved at most once.

Two live turns ran through the Docker stack. Turn 1 said "My name is Hassan";
turn 2 answered "Hassan" from the stored conversation.

## Setup

The venv lives at the repository root and uses Python 3.12. Postgres, Temporal,
and the UI run in Docker.

```
make up                                      # from the repo root
../../.venv/bin/pip install -e ".[dev]"      # from this directory, once
```

## Run

```
../../.venv/bin/python -m pytest             # from this directory
```

To run a real turn:

```
../../.venv/bin/python -m agent_service.worker       # terminal 1
../../.venv/bin/python -m agent_service.cli "hello"  # terminal 2
```

The worker and CLI read `TEMPORAL_ADDRESS` (default `localhost:7233`) and
`DATABASE_URL` (default `postgresql://ramonda:ramonda@127.0.0.1:5432/agent`).
