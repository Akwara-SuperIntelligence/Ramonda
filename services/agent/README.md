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
| talk §03 — the agent wakes on an event | `consumer.py` | A Kafka topic replaces the CLI as the trigger |
| EDA §4.1 — the event envelope | `events.py` | The first working contract between services |
| EDA §5 — dedupe before the workflow | `consumer.py`, `migrations/002_inbox.sql` | The inbox makes redelivery a no-op |
| EDA §4.3 — commands are the only write path | `consumer.py` | `SendMessage` is the only accepted event |
| talk §04 — one tool crosses the client boundary | `activities.py` (`send_user`) | The final answer becomes a message event |
| EDA §4.2 — `agent.message.composed` | `activities.py`, `relay.py` | The reply is published, not returned |
| EDA §5 — outbox, not a dual write | `migrations/003_outbox.sql`, `relay.py` | The turn and the event commit together |
| talk §04 — draft, ask, then act | `workflow.py`, `activities.py` | `send_email` waits on a signal |
| lesson 09 — three guards | `activities.py`, `consumer.py` | Policy, deadline, single-use resolution |
| EDA §4.2 — approval events | `events.py`, `migrations/004_approvals.sql` | Requested and resolved are separate events |
| talk §05 — the transcript is memory | `workflow.py` (`save_tool_step`) | Tool steps are rows, ordered by step |
| talk §05 — measure the cache | `activities.py` (`call_model`), `migrations/007_context.sql` | Hit and miss tokens stored per call |
| talk §05 — compact inside the warm window | `activities.py` (`compact`) | Old turns become a summary after a threshold |
| talk §05 — long output to a file | `activities.py` (`run_tool`, `read_file`) | The context gets a stored name, not a blob |
| talk §05 — stable section order | `activities.py` (`RULES`, `TOOLS`, `PROMPT_HASH`) | The prefix hash is recorded with every call |
| talk §04 — tool search | `activities.py` (`TOOL_SCHEMAS`, `get_tool_schema`) | Names in the prompt, schema fetched on demand |
| talk §05 — pin the prefix per conversation | `activities.py` (`pin_prompt`, `PROMPTS`) | A deploy adds a version; running turns keep theirs |
| talk §05 — hash each section | `activities.py` (`call_model`), `migrations/008_prompt_pin.sql` | Rules, tools, and memory hashed separately |
| talk §05 — pre-warm on typing | `consumer.py`, `activities.py` (`prewarm`) | One warm call, no turn |
| talk §02, §04 — sub-agents | `workflow.py` (`HelperWorkflow`, `delegate`) | Fresh context on its own queue; a report back |
| talk §04 — the main agent manages helpers | `workflow.py` (`helpers`, `collect`, `message_helper`, `stop_helper`) | Start without blocking, check, message, stop, collect |
| lesson 06 — a second loop | `workflow.py`, `worker.py` | The helper shares the pinned prompt; its calls record under a negative seq |
| talk §06, lesson 10 — evals from real failures | `tests/test_evals.py` | Repeat rule and memory recall, asserted on the live model |
| talk §02, §05 — memory layers | `activities.py` (`remember`, `note`, `recall`), `migrations/009_memories.sql` | Facts always in the prompt; scratch for one hour |
| lesson 07 — memory is stored so it can be recalled | `activities.py` (`load_history`, `recall`) | Facts and recent notes, not just the transcript |
| EDA §5 — serialise per conversation | `workflow.py`, `migrations/006_locks.sql` | A lock row is held for the whole turn |

## Verified

A worker was killed with `SIGKILL` while 108 turns were in flight. A new worker
completed all 200, with no duplicate or lost turn.

A duplicate effect token writes nothing, and a turn is saved at most once.

Two live turns ran through the Docker stack. Turn 1 said "My name is Hassan";
turn 2 answered "Hassan" from the stored conversation.

An event published to Redpanda started a turn with `org_id=acme`. Delivering the
same event again produced no second turn.

The same turn wrote one outbox row. The relay published it, and the delivery
client printed `hello` from `agent.message.composed`.

A live `send_email` stopped at an approval. Approving ran the effect once;
denying a second request ran nothing; an unanswered request expires in the test.

A live turn stored `user`, `tool`, `assistant` in that order, so the transcript
shows the work the agent did.

The cache is size-gated, measured against the live API with identical requests
spaced twelve seconds apart: 153 tokens gave 0 hits, 431 gave 256, 830 gave 640,
1820 gave 1664. Our chat prompts start near 150 tokens, so zero hits is expected
until a conversation grows. History is now sent as real messages, so each turn
repeats the previous prompt as a prefix instead of rewriting one user string.

A live turn fetched `send_email`'s schema with `get_tool_schema` and answered
from it. A live compaction run summarised twelve turns with the real model.

A live turn stored "my name is Hassan" with `remember`; the next turn answered
"Your name is Hassan" from the injected fact.

A live turn delegated to a helper and reported its answer. The helper's second
model call hit the cache on the shared prefix: 128 tokens.

A live turn started two helpers, listed them with `helpers`, and collected both
reports before answering.

## Known limits

Two behaviours are mitigations, not guarantees, and one is a lease. They are
recorded here so a later change does not assume more than the code provides.

- **The repeat rule is a prompt line, not a guard.** The model repeated
  `send_email` after it succeeded; the second request was denied, and the answer
  said nothing had been sent although the first call had. The rule is the
  cheapest fix and a live run obeyed it, but a new model can ignore it. An eval
  that replays this scenario is the real enforcement.
- **Serialisation is verified manually.** The lock has a unit test; the
  end-to-end order was shown against the real stack. The time-skipping test
  server expires activity timeouts while a second workflow waits, so the
  concurrent test was removed. Add it when CI has a server that does not skip
  time.
- **The prompt cache is size-gated.** Below roughly 250 tokens this provider
  records no hits at all; above that it caches in blocks. The hit ratio stays
  near zero for short conversations and rises as they grow.
- **Pre-warm depends on the client.** A typing event must be published for the
  prefix to warm. Nothing else sends it yet. Provider windows and our
  measurements are in [docs/CACHING.md](../../docs/CACHING.md).
- **Memory is per conversation.** A fact is visible only inside the conversation
  that wrote it. A cross-conversation profile needs an actor identity we do not
  pass yet.
- **Scratch is one hour.** The interval is fixed in the query, not configurable.
- **A failed turn terminates its helpers.** The default parent close policy is
  terminate; a budget failure drops the children with the parent.
- **Helper ids must be copied exactly.** The model dropped the `helper:` prefix
  once; the `helpers` tool let it recover. `collect all` avoids the copy.
- **The lock lease is one hour.** A terminated workflow leaves its row until
  expiry, and a turn longer than the lease can overlap with the next one. Renew
  the lease from inside long runs.

## Setup

The venv lives at the repository root and uses Python 3.12. Postgres, Temporal,
the UI, and Redpanda run in Docker.

```
make up                                      # from the repo root
../../.venv/bin/pip install -e ".[dev]"      # from this directory, once
```

## Run

```
../../.venv/bin/python -m pytest             # from this directory
```

To run a real turn, start the worker, then either the CLI or the consumer:

```
../../.venv/bin/python -m agent_service.worker        # terminal 1
../../.venv/bin/python -m agent_service.consumer      # terminal 2
../../.venv/bin/python -m agent_service.relay         # terminal 3
../../.venv/bin/python -m agent_service.delivery      # terminal 4
../../.venv/bin/python -m agent_service.cli "hello"   # or publish an event
../../.venv/bin/python -m agent_service.approve <id> approved
```

Publish an event to `agent.commands`:

```
echo '{"event_id":"e1","type":"agent.command.send_message","org_id":"acme",
"subject":{"conversation_id":"c1"},"payload":{"text":"hello"}}' \
  | docker compose exec -T redpanda rpk topic produce agent.commands
```

The worker, consumer, and CLI read `TEMPORAL_ADDRESS` (default
`localhost:7233`), `DATABASE_URL` (default
`postgresql://ramonda:ramonda@127.0.0.1:5432/agent`), and `KAFKA_BROKERS`
(default `localhost:9092`).
