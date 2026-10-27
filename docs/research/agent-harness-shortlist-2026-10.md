# Agent harness shortlist for a fixed-verb, auditable document workflow (2026-10)

Researched 2026-10-27 against GitHub repos at `main`, source files, release feeds, `pyproject.toml`/licences, and vendor docs. Scope: Python/FastAPI, six fixed verbs (`retrieve`, `fetch_source`, `extract`, `check`, `draft`, `ask_human`), one Run = one Workflow over a document set, an Artifact a person signs, no chat history, bounded steps/time, every model and tool call traced, human stop/inspect.

**Bottom line:** none of the agent frameworks is a workflow harness. They all assume the model chooses the next tool; your Workflow is data and the next step is fixed. The recommended architecture is **PydanticAI slim for the model/tool/trace layer + a ~250-line workflow interpreter you own + Procrastinate on Postgres**. If "do not write the step loop" is a hard constraint, take **LangGraph** instead — it is the only candidate that gives you the step engine, checkpointing, and interrupt/resume out of the box. Ranked by least adaptation: **PydanticAI (slim) → LangGraph → OpenAI Agents SDK → smolagents → Langroid → Agno → Claude Agent SDK**. For durability inside a bank: **Procrastinate** (pure Postgres) first; Hatchet if you want a workflow platform; Temporal only if runs get long; Inngest no.

---

## 1. Category correction (read this first)

Your "loop" is a deterministic interpreter over a step list, not a model-driven agent loop. The model is used *inside* `extract`, `check`, and `draft`; it does not decide whether to call `retrieve` next. Every framework below is built around the opposite assumption (model emits tool calls, loop executes them until a final answer). So:

- The part you must not write yourself is the **model port + typed tool schema + span emission**, not the step iteration.
- The step iteration is your product's domain logic and should be yours: roughly 200–300 lines, testable without an LLM.
- "Human can stop" is a **cooperative cancel flag persisted in Postgres**, not the frameworks' `interrupt()` (which pauses and resumes for approval).
- "Memory" is the **document set + append-only evidence ledger**, not a message list. Chat-history machinery is a liability to strip, not a feature to adopt.

This is the main reason the ranking below is not the usual "most popular framework" ranking.

---

## 2. (a) Ranked shortlist

| Rank | Candidate | Why it fits this shape | Why it does not | Verdict |
|---|---|---|---|---|
| **1** | **PydanticAI (install `pydantic-ai-slim`)** | MIT; model-agnostic; Pydantic tool schemas; OTel/Logfire spans; Temporal/DBOS/Prefect/Restate durability backends; deferred-tool approvals; typed outputs | v2 is a platform now: 3,896-line `_agent_graph.py`, 1,592 open issues/PRs, `message_history` + compaction + "capabilities"/"harness"; high release cadence | **Adopt the model/tool/trace layer; ignore the agent loop.** Pair with Procrastinate. |
| **2** | **LangGraph** | MIT; only candidate with first-class explicit `StateGraph`, Postgres checkpointer, `interrupt()`/resume, per-superstep checkpoints; 44k stars | Pulls `langchain-core`; graph is code, your Workflow is data (needs a compiler); thread/checkpoint model is chat-adjacent; overkill for a linear 6-verb list | **Adopt only if you want the step engine for free.** Otherwise use PydanticAI + queue. |
| **3** | **OpenAI Agents SDK** | MIT; good function tools, approvals, serializable `RunState`; huge community | `run.py` is 2,935 lines and `_run_impl` alone is ~2,300 lines; sessions/compaction baked in; tracing defaults to OpenAI Traces; OpenAI-first | **Copy the approval/RunState ideas; do not adopt the runtime.** |
| **4** | **smolagents** | Apache-2.0; by far the smallest real loop (~75 lines); `max_steps`; simple `@tool` | v1.26.0 is from 2026-05-29 (release-stale); 1,018 open issues/PRs; ReAct/code-writing agent with `AgentMemory`; no durable state | **Copy the loop shape as a reference; do not ship the package.** |
| **5** | **Langroid** | MIT; active; clean task abstractions; 4.1k stars | Hard Python cap `<3.14`; chat/`ChatDocument` is the substrate; multi-agent task loops, not a fixed step graph | No. |
| **6** | **Agno** | Apache-2.0; active; has workflows; 42.9k stars | `_run.py` is 6,617 lines; 1,936 open issues/PRs; "self-improving agent platform"; enormous surface | No. |
| **7** | **Claude Agent SDK (Python)** | MIT wrapper; hooks/permissions; strong Claude models | Not a Python loop: it drives a bundled, closed Claude Code CLI; Anthropic-only; 598 open issues/PRs; releases are mostly CLI bumps; sessions | No. |
| — | Inngest AgentKit | Durable execution is interesting | TypeScript-only; last push 2026-04-29; 956 stars; not a Python option | No. |
| — | Mastra | — | TypeScript; Apache-2.0 with an `ee/` carve-out | No. |
| — | DSPy | MIT; excellent prompt optimizer | **Not a harness**: no run state, step budget, tool registry, or interrupts | Optional offline only. |
| — | Temporal | MIT SDK; best-in-class durable execution | **Not a harness**: no model port, tool registry, or context assembler; self-hosted cluster | Durability option, not a harness. |

"Smallest" needs a definition. If it means **fewest lines of loop**, smolagents wins at ~75 lines. If it means **least new code plus the five production requirements** (fixed verbs, step-by-step, trace, stop, no chat), PydanticAI slim plus a ~250-line runner wins. The ranking uses the second definition, because the first still leaves you building durability, tracing, and a context assembler.

### 2.1 Fit against the five hard requirements

| Candidate | Fixed 6-verb registry | Step-by-step, not model-chosen | Per-run trace | Human stop (free, not just pause) | No chat memory |
|---|---|---|---|---|---|
| **PydanticAI** | Yes (tools) | Via your runner | Yes (OTel/Logfire) | Via your cancel flag | Yes (do not pass `message_history`) |
| **LangGraph** | Yes (nodes) | **Yes** (`StateGraph`) | Partial (LangSmith, commercial) | Partial (`interrupt()` pauses; stop needs flag) | Yes (custom state) |
| **OpenAI Agents** | Yes (`@function_tool`) | No (model tool loop) | Partial (OpenAI backend by default) | Partial (approvals; stop needs flag) | No (sessions/compaction) |
| **smolagents** | Yes (`@tool`) | Yes (fixed `while`) | No (logging only) | Partial (flag only) | No (`AgentMemory`) |
| **Langroid** | Yes (`ToolMessage`) | Partial (task loop) | No | No | No (`ChatDocument`) |
| **Agno** | Yes (`Toolkit`) | Partial (workflows exist, agent loop dominates) | Partial (integrations) | Partial (`continue_run`) | No (`AgentSession`) |
| **Claude Agent SDK** | Via MCP tools | No (CLI tool loop) | Partial (hooks) | Partial (permission callback) | No (CLI sessions) |

---

## 3. Q1: framework facts

### 3.1 Licence, activity, and what the loop actually is

| Framework | Licence | Latest release (2026) | Where the loop lives / size | Explicit step graph vs free-running ReAct |
|---|---|---|---|---|
| **OpenAI Agents SDK** | MIT [1] | v0.24.0, 2026-10-15 [4] | `src/agents/run.py` = 2,935 lines; `AgentRunner._run_impl` starts L629 and runs to EOF; `while True` at L1032; a single ~2,300-line method [2] | No declarative graph. Agents + handoffs + tool loop until final output or `max_turns`; effectively free-running [2] |
| **Claude Agent SDK** | MIT [8] | v0.2.174, 2026-10-24 [10] | No Python agent loop. Python package spawns the bundled Claude Code CLI; releases are "Updated bundled Claude CLI to version 2.1.310" [9][10] | No graph; Claude Code's own model-driven tool loop; subagents; sessions [9][11] |
| **PydanticAI** | MIT [12] | v2.62.0, 2026-10-26 [15] | `pydantic_ai_slim/pydantic_ai/_agent_graph.py` = 3,896 lines; four node classes: `UserPromptNode` L726, `ModelRequestNode` L1638, `CallToolsNode` L2721, `SetFinalResult` L3245; no small loop [13] | Graph-capable via `pydantic_graph`, but the default `Agent` is a model-driven tool loop; explicit graphs are a separate API [12][13] |
| **LangGraph** | MIT [20] | 1.2.18, 2026-10-26 [23] | `libs/langgraph/langgraph/pregel/_loop.py` = 2,172 lines; `PregelLoop.tick` L650 + `after_tick` L700 (~130 lines of loop); task execution in `_runner.py` [21] | **Explicit `StateGraph`** is the product; superstep execution, checkpoints, interrupts [24][25] |
| **Langroid** | MIT [26] | 0.69.16, 2026-10-25 [29] | `langroid/agent/task.py` = 2,562 lines; `Task.run` L792 with `while True` L849 (~150 lines) [27] | Task loops with `done_sequences`; no declarative graph; free-running multi-agent [26][27] |
| **smolagents** | Apache-2.0 [30] | v1.26.0, 2026-05-29 [32] | `src/smolagents/agents.py` = 1,813 lines; `MultiStepAgent._run_stream` L540–L613 (~75 lines) [31] | No graph; fixed `while` loop with optional planning interval; ReAct/code agent [31] |
| **Agno** | Apache-2.0 [34] | v3.1.10, 2026-10-23 [36] | `libs/agno/agno/agent/_run.py` = 6,617 lines; `_run` L367, `_run_stream` L777 [35] | Has workflows, but the agent loop is model-driven and enormous [34][35] |
| **Inngest AgentKit** | Apache-2.0 [37] | Last push 2026-04-29 [37] | TypeScript; not applicable to Python | Deterministic routing networks in TS [37] |
| **DSPy** | MIT [40] | 3.4.1, 2026-10-12 [41] | No runtime loop; `Predict` is one model call; `ReAct` is a module, not a harness [40] | Module/pipeline programming, not a run graph |
| **Temporal** | MIT (Python SDK) [42] | Active (pushed 2026-10-27) [42] | Durable workflow replay; workflow code is yours | No graph DSL; workflows/activities; signals/queries [43] |

### 3.2 Tools, tracing, HITL, chat memory

| Framework | Tool registration / schema | Tracing hooks | Human-in-the-loop interrupt | Assumes chat history |
|---|---|---|---|---|
| **OpenAI Agents** | `@function_tool`; Pydantic/dataclass → strict JSON schema; MCP tools [1][2] | Built-in tracing; **defaults to OpenAI Traces dashboard**, needs an OpenAI key unless `set_tracing_disabled(True)` [5] | Tool approvals (`needs_approval`) + serializable `RunState` resume [7] | **Yes**: `Session`, `conversation_id`, automatic compaction [4][6] |
| **Claude Agent SDK** | `@tool` + in-process MCP server; JSON schema; also full Claude Code toolset [9] | Hooks and message stream; no OTel span API surfaced in the SDK README [9] | `can_use_tool` permission callback, permission modes, hooks [9] | **Yes**: sessions, resume, compaction [9] |
| **PydanticAI** | `@agent.tool`, `Toolset`, Pydantic validation and schema generation [12] | OTel/Logfire instrumentation for agent, model, and tool spans [52] | Deferred tool calls (`DeferredToolRequests`) and resume [18] | **Yes**: `message_history`, `CompactionPart`, `SummarizingCompaction`/`SlidingWindowCompaction`/`RelevanceCompaction` [15][19] |
| **LangGraph** | LangChain `BaseTool`/`ToolNode`; Pydantic `args_schema` [20] | LangSmith-native (commercial); OTel only via LangSmith ingestion or external instrumentation, not core [20][24] | `interrupt()` + checkpointer; resume with `Command(resume=...)` [25] | **No**: state is an arbitrary `TypedDict`; `MessagesState` is optional. Thread/checkpoint model still applies [24] |
| **Langroid** | `ToolMessage` classes with Pydantic request/response; function calling [26] | Structured logging; no OTel-native tracing [26] | No first-class durable interrupt | **Yes**: `ChatDocument`/dialog is the substrate [26][27] |
| **smolagents** | `@tool`, `Tool` class, `validate_arguments`, JSON schema from type hints/docstrings [31] | Rich logging + step callbacks; its `monitoring.py` is Rich-based, not OTel [53] | `interrupt()` sets a flag; raises at next step; no resume [31] | **Yes**: `AgentMemory` (`TaskStep`, `ActionStep`, `PlanningStep`) [31] |
| **Agno** | `@tool`, `Toolkit`, Pydantic [34] | Logging + integrations; not a core one-span-per-step API [34] | `continue_run`/paused run status [35] | **Yes**: `AgentSession`, session summaries, past-session search [34] |
| **DSPy** | `dspy.Tool` exists, but no runtime registry/loop | Callbacks/experiment tracking, not run-level audit [40] | No | No (modules take messages, but no session state) |
| **Temporal** | Activities are your tools; no registry/schema | OTel interceptors/metrics supported [42] | Signals/queries + durable timers [43] | No |

---

## 4. Q2 / (b): top pick — PydanticAI slim + a 250-line runner + Procrastinate

### 4.1 What to depend on

Install **`pydantic-ai-slim`**, not the `pydantic-ai` meta-package. The meta-package currently depends on `pydantic-ai-slim[openai,anthropic,google,cli,mcp,evals,web,logfire]`, which is a large default surface [14]. Use only the provider extra you actually need.

| Module | Why keep it |
|---|---|
| `pydantic_ai.models` + one provider extra | The model port: `Model.request(...)`, provider adapters, structured output, usage, timeouts [12] |
| `pydantic_ai.tools` / `toolsets` and `_function_schema.py` | JSON-schema generation and argument validation for the six verbs [12] |
| `pydantic_ai.messages` | Typed request/response and tool-call parts; use per-call, not as history [12] |
| `pydantic_ai.settings`, `usage`, `exceptions` | Model settings, token/cost accounting, typed errors [12] |
| `pydantic_ai.models.instrumented` | OTel spans for model calls [52] |
| `DeferredToolRequests` / `DeferredToolResults` | Only if an `ask_human` step needs an approval gate [18] |

### 4.2 What to copy (if you want a zero-framework core)

- `_function_schema.py` — Pydantic type-hint → JSON schema; small and self-contained.
- The `ToolDefinition` shape — name, description, JSON schema, handler; use it as your verb registry value type.
- The OTel attribute naming from `pydantic_ai.models.instrumented` — keeps spans compatible with GenAI tooling.

### 4.3 What to build (your thin layer, ~250–350 lines)

- `app/workflow/runner.py` — iterate `workflow.steps`; check deadline, step budget, `cancel_requested`; dispatch verb; commit result; enqueue next step.
- `app/workflow/verbs/*.py` — six handlers, each `async def run(ctx) -> StepResult`; only `extract`/`check`/`draft` call a model.
- `app/workflow/context.py` — assemble per-step context from documents + evidence ledger; token budget; deterministic order.
- `app/workflow/ledger.py` — append-only evidence rows with provenance.
- `app/workflow/trace.py` — OTel span per run/step/model/tool; event log with redaction.
- `app/workflow/store.py` — `workflow_runs`, `workflow_steps`, idempotency keys, cancel flag.
- `app/workflow/queue.py` — Procrastinate tasks: one task per step, `run_id:step_index` idempotency.

Sketch (the whole "loop"):

```python
async def run(run_id: UUID) -> None:
    run = await store.claim(run_id)
    while run.next_step < len(run.workflow.steps):
        if run.cancel_requested:
            return await store.stop(run_id, reason="human")
        if run.deadline_expired:
            return await store.fail(run_id, reason="deadline")
        step = run.workflow.steps[run.next_step]
        ctx = assemble(step, run)                  # documents + ledger slice
        with trace.step(run_id, step):
            result = await VERBS[step.verb](ctx, step.args)
        await store.commit_step(run_id, step.index, result)  # + outbox next
        run = await store.advance(run_id)
```

This is a workflow interpreter, not an agent loop. It is testable with a fake model port; no framework owns it.

### 4.4 What to delete / ignore

- `pydantic_ai.agent` and `_agent_graph.py` — the four-node model-driven loop (~2,900 lines) [13].
- `capabilities/` — Harness, Memory, Compaction, CodeMode, Shell, Workspace.
- `message_history`, `CompactionPart`, `SummarizingCompaction`, `SlidingWindowCompaction`, `RelevanceCompaction` [15][19].
- `durable_exec/` if you use Procrastinate (keep it only if you choose Temporal).
- `mcp/`, `evals/`, `cli/`, `web/`, `realtime/`, `batch/`, `profiles/`.
- The `pydantic-ai` meta-package extras [14].

### 4.5 Fallback if "do not write the step loop" is absolute

Use **LangGraph**: `StateGraph`, `PostgresSaver`, `interrupt()`, `Command(resume=...)` [24][25]. Compile each Workflow definition (data) into a graph with six node types. You still write the model port (LangChain chat models) and the data→graph compiler, and you carry `langchain-core` [22]. It is the only candidate that gives you the durable step engine out of the box.

---

## 5. Q3: memory and context compaction for a non-chat agent

### 5.1 The four memory layers

1. **Document store** — immutable, content-addressed (SHA-256), versioned; page/offset index for citations. The model never "remembers" documents; it is given a slice.
2. **Evidence ledger** — append-only rows:
   `evidence_id, run_id, step_id, doc_id, doc_version, page, char_start, char_end, quote_hash, model_call_id, confidence, created_at`.
   No updates, no deletes; a correction is a new row with `supersedes`.
3. **Run state** — `run_id, workflow_id, workflow_version, step_index, status, attempt, cancel_requested, deadline, outputs`.
4. **Context window** — rebuilt per step from 1+2+3; never persisted as "memory".

### 5.2 What "compaction" means here

It means **evidence selection under a token budget**, not conversation summarization:

- Retrieve candidate evidence for the current step (by verb + document scope + prior findings).
- Dedupe by `quote_hash`; order deterministically (doc id, page, offset).
- Pack exact quotes with provenance until the step's token budget is reached.
- If over budget, drop lowest-relevance items and emit a `context_truncated` trace event listing what was dropped.
- Summarize only for the human-readable Artifact; never summarize the ledger and never feed a summary as evidence.

### 5.3 Which frameworks impose chat-shaped memory, and how hard to strip

| Framework | Memory primitive | Chat-shaped? | Strip effort (estimate) | How |
|---|---|---|---|---|
| **OpenAI Agents** | `Session`, `conversation_id`, automatic compaction [4][6] | Yes | Medium (1–2 weeks) | Never pass `session=`/`conversation_id`; pass explicit input items per step; disable tracing; keep `RunState` only for resume |
| **PydanticAI** | `message_history`, `CompactionPart` [15][19] | Yes | Small–medium (1–3 days) | Fresh `message_history=[]` per step, or call `Model.request()` directly; never enable compaction |
| **LangGraph** | `thread_id` checkpoint; `MessagesState` common [24] | No, if you define state | Small (2–5 days) | Custom `TypedDict` with `documents`, `ledger`, `step_index`; do not use `MessagesState`; keep the checkpointer |
| **Langroid** | `ChatDocument` dialog/entity history [26] | Yes | Large (3–4 weeks) | Rewrite the task/entity layer; chat is the substrate |
| **smolagents** | `AgentMemory` steps [31] | Yes | Large (2–4 weeks) | Replace `write_memory_to_messages` and the step classes; the loop is message-bound |
| **Agno** | `AgentSession`, summaries, past-session search [34] | Yes | Large (4+ weeks) | Bypass sessions; the run loop expects them |
| **Claude Agent SDK** | CLI session, resume, compaction [9] | Yes | Extra-large / not feasible | Opaque CLI owns history; you can only start a new session |
| **DSPy** | None | No | n/a | n/a |

The important asymmetry: LangGraph's checkpoint is *useful* for audit even though its thread model looks chat-like, because you control the state schema. OpenAI/PydanticAI/Claude sessions are not useful here; they persist exactly the thing you do not want.

---

## 6. Q4: minimal auditable loop — component coverage

| Component | What it must do | PydanticAI | LangGraph | OpenAI Agents | smolagents | Temporal / Procrastinate |
|---|---|---|---|---|---|---|
| **Loop** | Iterate fixed steps; stop at end/deadline/cancel | Partial (model-driven `Agent`; use `Model.request` directly) | **Yes** (`StateGraph`) | Partial (agent loop, not step graph) | **Yes** (~75 lines) | **Yes** (workflow / task chain) |
| **Step budget** | Max steps + wall-clock deadline per Run | Partial (`UsageLimits`) | Partial (`recursion_limit`) | Partial (`max_turns`) | **Yes** (`max_steps`) | **Yes** (timeouts/timers) |
| **Tool registry** | Fixed six verbs; JSON schema; allowlist; versioning | **Yes** (tools/toolsets) | Via LangChain tools | **Yes** (`@function_tool`) | **Yes** (`@tool`) | No (you build activities) |
| **Context assembler** | Documents + ledger slice; token budget; provenance | No | No | No | No | No |
| **Model port** | Provider-agnostic; structured output; timeout; usage | **Yes** | No (LangChain models) | **Yes** | **Yes** | No |
| **Trace emitter** | Span per run/step/model/tool; redaction; immutable | **Yes** (OTel/Logfire) | LangSmith-native; OTel via external instrumentation | Built-in, OpenAI backend by default | Logging/callbacks only | OTel / job events |
| **Interrupt/resume** | Pause for approval; resume; cancel | Deferred tools | **Yes** (`interrupt()`) | Approvals + `RunState` | Flag only | Signals / manual job state |
| **Error/retry policy** | Typed errors; retry classes; idempotency; DLQ | Partial | Per-node retry | Partial | Weak | **Yes** (Temporal/queue) |

No candidate gives you the context assembler or the evidence ledger. Those are your product.

---

## 7. Q5: durable execution inside a bank

### 7.1 Correcting the premise

`arq` is Redis-based [49]; `dramatiq` is Redis/RabbitMQ-based [48]; only **Procrastinate** and **Hatchet** are Postgres-backed [44][46]. So "(a) Postgres-backed queue (arq, dramatiq, ...)" mixes backends.

| Option | Backend / control plane | Ops footprint | Bank fit | Verdict |
|---|---|---|---|---|
| **Procrastinate** | PostgreSQL 13+; task definitions, locks, retries in Postgres [44][45] | One database; Python worker; no broker, no external control plane | **Best**: single-tenant, air-gapped, one DB to back up/audit; MIT; 3.10.0 (2026-09-21) | **v1 default.** You add step state and idempotency, but the queue is boring and inspectable. |
| **Hatchet** | Postgres as durability layer for runtime + observability; self-hosted server/dashboard/workers [46][47] | A platform (server + dashboard + workers) on Postgres | Good if you want a workflow UI and durable DAGs; MIT; very active (v0.114.9, 2026-10-27) | Strong second. v0.x maturity risk; more moving parts than a bank may want. |
| **Temporal** | Self-hosted Temporal Service + persistence DB; cluster [42][43] | Heaviest: server cluster, DB, upgrades, versioning | Fits technically; overkill for runs bounded in minutes | Only if runs get long, need timers/signals/versioning, or you already operate Temporal. |
| **Inngest** | Self-hosted Inngest server with Redis queue/state + Postgres [51] | Server + Redis + Postgres; cloud-first SDK gravity | Weak: extra services, external-control-plane assumptions, AgentKit is TS-only [37] | No for an air-gapped bank. |
| **arq** | Redis [49] | Redis | Weak: Redis dependency, last push 2026-04-16 | No. |
| **Dramatiq** | Redis or RabbitMQ [48] | Broker | **Licence: LGPL-3.0** [48] | No without legal review. |

### 7.2 Recommended shape

- **v1:** Procrastinate + Postgres. One task per step, `run_id:step_index` idempotency key, `SELECT ... FOR UPDATE SKIP LOCKED` semantics, retries with typed error classes.
- **Human stop:** `POST /runs/{id}/stop` writes `cancel_requested=true`; the worker checks it at every step boundary and before every model/tool call; emits `run.stopped`, sets status `stopped_by_human`; the Artifact is not signable.
- **Restart safety:** commit step output + enqueue next step in one transaction (outbox). On restart, re-claim the job and re-run only if the step has no committed output.
- **Upgrade path:** if you outgrow a linear queue (parallel branches, DAG UI, long waits), move to Hatchet; if you need cross-service orchestration and long timers, move to Temporal. Do not start with Temporal for a 10-step, 5-minute run.

---

## 8. (c) Blunt findings

1. **This is a category error.** None of these is a fixed-verb workflow harness; all are model-driven tool loops. You will write the step interpreter regardless — keep it, because it is your audit boundary. [1][12][20][34]
2. **"Lightweight" OpenAI Agents SDK is not lightweight.** `run.py` is 2,935 lines; `_run_impl` is a ~2,300-line method with the `while True` at L1032; sessions, compaction, sandbox, realtime, and guardrails are in the same path. [2][4]
3. **OpenAI tracing is a data-egress decision, not a feature.** Tracing is on by default and exports to the OpenAI Traces dashboard; even non-OpenAI models need an OpenAI API key for tracing unless you disable it. For a bank, `set_tracing_disabled(True)` on day one, then emit your own OTel spans. [5]
4. **Claude Agent SDK is a wrapper, not a Python harness.** The README says the Claude Code CLI is bundled; releases are CLI version bumps; the loop, tools, sessions, and compaction live in the closed CLI. You cannot copy the loop, and you are locked to Anthropic. [9][10][11]
5. **PydanticAI v2 is now a platform.** 3,896-line agent graph, 1,592 open issues/PRs, `message_history`, compaction parts, capabilities, harness, code mode, shell, workspace. It is still the best *library* here — but install `pydantic-ai-slim`, pin the version, and do not adopt the harness. [13][14][15]
6. **LangGraph is the only first-class graph/checkpoint/interrupt engine.** It is also a `langchain-core` dependency and a code-defined graph, while your Workflows are data. Use it only if "step engine for free" outweighs the compiler and dependency cost. [20][22][24][25]
7. **smolagents has the smallest loop and the stalest release.** ~75 lines is the right shape to copy; v1.26.0 is from 2026-05-29, with 1,018 open issues/PRs, and the agent is a code-writing ReAct loop with `AgentMemory`. Copy the pattern, not the package. [31][32]
8. **Agno is marketing-shaped.** "The self-improving agent platform", 42.9k stars, 1,936 open issues/PRs, and a 6,617-line `_run.py`. Stars are not a maintainability metric. [34][35][36]
9. **Python and licence traps are concrete.** Langroid hard-caps `requires-python = "<3.14,>=3.10"`; Dramatiq is LGPL-3.0; arq is Redis-based and quiet since 2026-04-16; LangGraph lists classifiers only through 3.13; smolagents declares only `requires-python >=3.10` and no 3.14 classifier. Check these before the bank's dependency scan. [28][48][49][22][33]
10. **"Human-in-the-loop interrupt" is not "human can stop".** `interrupt()`, approvals, and deferred tools pause and resume for a decision; a kill switch is a persisted `cancel_requested` flag checked between steps and before every model/tool call. Build the latter explicitly. [7][18][25]

Not in the ten: DSPy and Temporal are not harnesses at all — DSPy is a prompt/module compiler and Temporal is durable execution; neither has a tool registry, context assembler, or evidence ledger [40][42][43]. Inngest AgentKit and Mastra are TypeScript, so they are out of scope for a Python/FastAPI product [37][38][39].

---

## 9. (d) Sources

1. OpenAI Agents SDK repo — https://github.com/openai/openai-agents-python
2. OpenAI Agents SDK `run.py` — https://github.com/openai/openai-agents-python/blob/main/src/agents/run.py
3. OpenAI Agents SDK `pyproject.toml` — https://github.com/openai/openai-agents-python/blob/main/pyproject.toml
4. OpenAI Agents SDK v0.24.0 release — https://github.com/openai/openai-agents-python/releases/tag/v0.24.0
5. OpenAI Agents SDK tracing docs — https://openai.github.io/openai-agents-python/tracing/
6. OpenAI Agents SDK sessions docs — https://openai.github.io/openai-agents-python/sessions/
7. OpenAI Agents SDK human-in-the-loop docs — https://openai.github.io/openai-agents-python/human_in_the_loop/
8. Claude Agent SDK Python repo — https://github.com/anthropics/claude-agent-sdk-python
9. Claude Agent SDK README — https://github.com/anthropics/claude-agent-sdk-python/blob/main/README.md
10. Claude Agent SDK v0.2.174 release — https://github.com/anthropics/claude-agent-sdk-python/releases/tag/v0.2.174
11. Claude Agent SDK overview — https://docs.claude.com/en/api/agent-sdk/overview
12. PydanticAI repo — https://github.com/pydantic/pydantic-ai
13. PydanticAI `_agent_graph.py` — https://github.com/pydantic/pydantic-ai/blob/main/pydantic_ai_slim/pydantic_ai/_agent_graph.py
14. PydanticAI `pyproject.toml` — https://github.com/pydantic/pydantic-ai/blob/main/pyproject.toml
15. PydanticAI v2.62.0 release — https://github.com/pydantic/pydantic-ai/releases/tag/v2.62.0
16. PydanticAI durable execution — https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/
17. PydanticAI compaction — https://pydantic.dev/docs/ai/capabilities/compaction/
18. PydanticAI deferred tools — https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/
19. PydanticAI message history — https://pydantic.dev/docs/ai/core-concepts/message-history/
20. LangGraph repo — https://github.com/langchain-ai/langgraph
21. LangGraph `pregel/_loop.py` — https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/langgraph/pregel/_loop.py
22. LangGraph `pyproject.toml` — https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/pyproject.toml
23. LangGraph 1.2.18 release — https://github.com/langchain-ai/langgraph/releases/tag/1.2.18
24. LangGraph persistence docs — https://docs.langchain.com/oss/python/langgraph/persistence
25. LangGraph interrupts docs — https://docs.langchain.com/oss/python/langgraph/interrupts
26. Langroid repo — https://github.com/langroid/langroid
27. Langroid `task.py` — https://github.com/langroid/langroid/blob/main/langroid/agent/task.py
28. Langroid `pyproject.toml` — https://github.com/langroid/langroid/blob/main/pyproject.toml
29. Langroid 0.69.16 release — https://github.com/langroid/langroid/releases/tag/0.69.16
30. smolagents repo — https://github.com/huggingface/smolagents
31. smolagents `agents.py` — https://github.com/huggingface/smolagents/blob/main/src/smolagents/agents.py
32. smolagents v1.26.0 release — https://github.com/huggingface/smolagents/releases/tag/v1.26.0
33. smolagents `pyproject.toml` — https://github.com/huggingface/smolagents/blob/main/pyproject.toml
34. Agno repo — https://github.com/agno-agi/agno
35. Agno `_run.py` — https://github.com/agno-agi/agno/blob/main/libs/agno/agno/agent/_run.py
36. Agno v3.1.10 release — https://github.com/agno-agi/agno/releases/tag/v3.1.10
37. Inngest AgentKit repo — https://github.com/inngest/agent-kit
38. Mastra repo — https://github.com/mastra-ai/mastra
39. Mastra LICENSE — https://github.com/mastra-ai/mastra/blob/main/LICENSE.md
40. DSPy repo — https://github.com/stanfordnlp/dspy
41. DSPy 3.4.1 release — https://github.com/stanfordnlp/dspy/releases/tag/3.4.1
42. Temporal Python SDK — https://github.com/temporalio/sdk-python
43. Temporal self-hosted guide — https://docs.temporal.io/self-hosted-guide
44. Procrastinate repo — https://github.com/procrastinate-org/procrastinate
45. Procrastinate docs — https://procrastinate.readthedocs.io/en/stable/
46. Hatchet repo — https://github.com/hatchet-dev/hatchet
47. Hatchet self-hosting docs — https://docs.hatchet.run/self-hosting
48. Dramatiq repo (LGPL-3.0) — https://github.com/Bogdanp/dramatiq
49. arq repo (Redis) — https://github.com/python-arq/arq
50. Inngest Python SDK — https://github.com/inngest/inngest-py
51. Inngest self-hosting docs — https://www.inngest.com/docs/self-hosting
52. PydanticAI Logfire/OTel integration — https://pydantic.dev/docs/ai/integrations/logfire/
53. smolagents `monitoring.py` — https://github.com/huggingface/smolagents/blob/main/src/smolagents/monitoring.py

---

### Method note

Star counts, open-issue counts, licence SPDX IDs, and last-push dates were read from the GitHub REST API on 2026-10-27. Release versions/dates were read from each repo's `releases.atom` feed. Loop line counts were measured from the `main` branch raw files on 2026-10-27; they will drift. Effort estimates in §5.3 are engineering judgement, not vendor claims.
