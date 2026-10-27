# The harness

The harness executes a Workflow. It is the only module allowed to call a model.

## Decision for v0.1

Three pieces, and only two are adopted.

| Piece | Choice | Why |
|---|---|---|
| Model, tools, tracing | `pydantic-ai-slim`, pinned, used as a library | model port, JSON-schema tool arguments, OTel spans |
| Step interpreter | about 250 lines we own, in the `harness` module | no candidate runs a fixed list of Steps |
| Durable jobs | Procrastinate on PostgreSQL | one queue, no broker, no control plane |

**The finding that decides it:** none of the candidates is a fixed-verb workflow harness. Every one of them assumes the model chooses the next tool. Our Workflow is data and the next Step is fixed, so the loop we would copy is the loop we do not want. Writing the interpreter is less work than stripping an agent loop down to it, and it is the audit boundary.

## What we use from `pydantic-ai-slim`

- `pydantic_ai.models` plus one provider extra: the model port, structured output, usage, timeouts.
- `pydantic_ai.tools`: argument schema and validation for the verbs.
- `pydantic_ai.messages`: typed request and response, per call only.
- `pydantic_ai.models.instrumented`: OpenTelemetry spans.
- `DeferredToolRequests`, only if `ask_human` needs an approval gate.

Install the slim package. The meta-package `pydantic-ai` pulls the agent, the CLI, MCP, evals and the web UI, and v2 is a platform: a 3,896-line agent graph, chat memory, and compaction. Pin it and ignore all of that.

## Never enabled

`Agent`, `_agent_graph.py`, `message_history`, every compaction strategy, `capabilities/`, `durable_exec/`, MCP, evals, CLI, web.

## The loop

```python
while run.next_step < len(workflow.steps):
    stop_if_cancelled(run)             # a Person pressed stop
    stop_if_over_budget(run)           # steps and deadline
    ctx = assemble(step, run)          # documents and ledger slice, token budget
    out = VERBS[step.uses](ctx, step.with_)
    store.commit_step(run, step, out)  # one transaction
    enqueue_next(run)
```

Fifteen lines of control flow. Everything else is the seven verbs.

## Memory, and what "compaction" means here

There is no conversation, so there is nothing to summarise. Four layers, and only one is a window:

1. **Documents** — immutable, content-addressed, index by page and offset.
2. **Evidence ledger** — append-only. A correction is a new row, never an edit.
3. **Run state** — step index, status, attempt, deadline, `cancel_requested`, step outputs.
4. **Context** — rebuilt for each Step, never stored.

"Compaction" here is **evidence selection under a token budget**: retrieve candidates for this Step's verb and scope, dedupe by quote hash, order deterministically, pack exact quotes with provenance. Over budget, drop the lowest relevance and record `context_truncated` on the Step.

A summary is for the Artifact a Person reads. It is never evidence, and it never goes into the ledger.

## The kill switch is not an interrupt

`interrupt()`, approvals and deferred tools pause a Run to ask for a decision. Stopping a Run is a different thing: a persisted `cancel_requested` flag, checked at every Step boundary and before every model or tool call.

Wire it in v0.1. "A Person can stop it" is part of what the product promises.

## What no framework gives us

The context assembler and the Evidence ledger. Both are ours, both are the product, and neither has an off-the-shelf substitute.

## Fallback

LangGraph, only if we refuse to own the interpreter. It is the one candidate with an explicit `StateGraph`, Postgres checkpoints and `interrupt()` with resume. The cost: it brings `langchain-core`, a graph defined in code while Workflows are data, and therefore a compiler from Pack data to nodes. More moving parts, less of it ours.

Do not adopt the OpenAI Agents SDK or the Claude Agent SDK for this shape. The first is a 2,935-line model loop with sessions and telemetry on by default; the second is a wrapper around a closed CLI.

## v0.2 changes one thing

v0.2 adds Artifact change requests: a Person asks for a change, the harness runs a bounded revision pass over the existing Artifact under the same Evidence rules, and a new Artifact version arrives with a diff and a new Signature.

That is one more verb, not a new architecture.
