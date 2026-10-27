# The harness

The harness executes a Workflow. It is the only module allowed to call a model.

## v0.1 does not build one

We copy one. The loop is a few hundred lines that are easy to get wrong, and the value is in the seven verbs, the Checks and the Evidence, not in the loop.

Selection criteria, in order:

1. Steps are explicit, not free-running ReAct.
2. No chat history is assumed.
3. Tracing hooks per run and per call.
4. Interrupt and resume for `ask_human`.
5. Python, permissive licence, active.
6. The model sits behind a port, so a provider swap is configuration.

## What the harness must do

- execute one Step at a time against a step budget and a time budget;
- refuse a verb that is not in the register;
- assemble context per Step by query, never by accumulation;
- emit one span per verb and one per model call, both tagged `run_id`;
- persist each Step's output so a restart resumes instead of repeating;
- stop for `ask_human` and stay stopped until a Person acts.

## Memory

The memory of a Run is its file: the Documents in scope, the Evidence so far, and the Artifact draft. It is rebuilt for each Step by a query, under a token budget.

There is no conversation, so there is no history to compact. Most of the difficulty in agent frameworks is managing a conversation this product does not have, which is the main reason to keep the harness small.

## What we throw away from whatever we copy

Chat history, memory stores, planners, multi-agent orchestration, vendor SDKs, prompt registries, and anything that keeps state outside PostgreSQL.

## Decision

Pending. The shortlist and the pick land here before any code. Research is running on which harness to copy, what to delete from it, and how it handles durable Runs.

## v0.2 changes the loop

v0.2 adds Artifact change requests: a Person asks for a change, the harness runs a bounded revision pass over the existing Artifact under the same Evidence rules, and a new Artifact version arrives with a diff and a new Signature.

That is one more verb, not a new architecture.
