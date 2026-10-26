# Architecture

An agent reads institutional knowledge and produces an artifact a client asked for: an investor report, a risk analysis, or the next brief of that kind. The knowledge is private. The artifact is the product.

The core is one Python process. Components call each other in-process through a public API. Apache Tika stays its own container, because it is a Java server. Postgres, and OpenSearch if retrieval uses it, stay their own containers because they are databases. The application deploys once.

A component is one reason the code changes. A pipeline step is not a component. If a small change has to touch several components, the boundary is wrong and the code moves.

## Components

### Ingestion

Changes when a source file comes out as different chunks.

Public API: `ingest(caller)`.

Inside: the Drive source, Tika, Unstructured, Docling, the hierarchical chunker, the LlamaIndex metadata extractors (`document_title`, `section_summary`, `prev_section_summary`, `excerpt_keywords`, `questions_this_excerpt_can_answer`), the document's label and access list, and the call to `retrieval.save`. Tables stay whole. Tika's text is not what gets chunked. Tika is called over HTTP at the container's `/rmeta` endpoint.

### Retrieval

Changes when a search comes back with different chunks. The agent uses this as a tool.

Public API: `save(caller, chunks)` and `search(query, caller, filters)`.

Inside: the document security label, the access list, the SQL filters, the hybrid index (vectors in Postgres, BM25 in OpenSearch), and re-ranking. OpenSearch is private to this component.

### Agent

Changes when a brief comes out as a different artifact.

Public API: `produce(brief) -> artifact`.

Inside: the router, the planner, the tools, the specialists, and the retry loop. The router decides which step needs `retrieval.search` and which step does not. Low confidence returns to the router. An investor report and a risk analysis are slices inside this component. They split into their own components only when a change to one no longer changes the other.

Before an artifact is released, the agent calls oversight.

### Oversight

Changes when a decision must be approved or recorded.

Public API: `approve(action)` and `record(who, what, why)`.

Inside: the human gate for a high-stakes release, the append-only audit log, and the later review of edge cases. Chunk size and search weights do not change this component.

## Who calls whom

The host is the single entry. Clients call the host. The host checks who is calling, starts a trace id, and calls `ingest`, `produce`, and `approve` with that caller and that trace id.

Ingestion may call `retrieval.save`. The agent may call `retrieval.search`, `oversight.approve`, and `oversight.record`. Retrieval and oversight call no other component.

## Outside the components

Evaluation and stress testing are on the map. Their arrows point at the agent. The agent does not call them to build an artifact, so they are not packages under `ramonda/`. They live in the test suite and call the host.

**Evaluation** scores the run after the artifact exists. Ragas, TruLens, and DeepEval do that scoring. The loop runs continuously against the host, not only when a person launches the suite once.

- Faithfulness compares the report with the chunks that were retrieved. A sentence in the report should be supported by those chunks.
- Relevance compares the report with the client’s brief. The report should cover what was asked.
- Precision and recall compare the chunks that came back with the chunks that should have come back. Precision asks whether the retrieved chunks were the right ones. Recall asks whether enough of the right ones were retrieved.
- Latency and cost compare the run with a time limit and a money limit.

Precision and recall need a known set of right chunks for that brief. The files ingested so far do not have that set.

**Stress testing** sends hostile briefs at `produce` and watches the artifact. Garak, PyRIT, and Lakera fire those attacks at the reasoning engine and the specialists. NeMo Guardrails is the check on the door of `produce`: it inspects the brief on the way in and the artifact on the way out. That check stays on the host until the rules have their own owner.

## Beside the components

Identity, logging, and observability are required, and they are not packages the components import. A cache and a message broker are not part of this monolith. Components call each other in-process. A broker waits until a long ingest, or sending the finished report, must continue after the request is gone.

**Identity.** Retrieval's filter is "only the rows this caller may see." Oversight's audit line is "who approved this release." The host verifies the identity provider's token once, at the door, and passes the caller into `search`, `produce`, and `approve`. The caller carries the user, the organisation, the groups, and the clearance. Ingestion reads Drive with its own credential, because that credential is not the client who may see a chunk.

**Logging.** When a file fails, the line says which component, which file or brief, and which step. Each component writes that with Python's `logging` module to standard output. The container keeps those lines. A line carries the component name, the action, and the id.

**Observability.** Evaluation's latency and cost scores need a clock and a count of model calls. The host's trace id is passed into every call. Each component logs how long its part took. The enricher and the agent log how many model calls they made. Evaluation reads those lines. A metrics collector comes later, when those lines are not enough to query.

## How the boundary is held

**Public surface.** Each component is a package. Its `__init__.py` exports the public functions and nothing else. A test fails the build when one component imports a module behind another's package root. `ramonda.agent` may import `ramonda.retrieval`. It may not import `ramonda.retrieval.search`.

**Data.** A component that stores rows gets its own Postgres schema and its own database user. Retrieval's user owns the document, access, and chunk rows. Oversight's user owns the audit log. Ingestion stores nothing. The files stay in Drive. The agent gets a schema only when an artifact needs a row of its own. No component has a login to another component's schema. Reading another component's data goes through its public functions.

**The move.** The existing scripts live in `ramonda/ingestion/`. The package root exports `ingest`, which runs Tika, Unstructured, Docling, chunk, and enrich in that order, then labels each file and calls `retrieval.save`. Agent and oversight get a package when their first real code arrives. Empty packages are not part of the move.

## Layout

```
ramonda/
  host.py
  ingestion/
  retrieval/
  agent/
  oversight/
```

`host.py` wires the public functions and is the only module a client process starts. It is not a fifth component. Ingestion and retrieval exist today, as `ramonda/ingestion/` and `ramonda/retrieval/`. The container runs `python -m ramonda.ingestion`. Tika stays the service in `docker-compose.yml`.
