# Architecture

An agent reads institutional knowledge and produces an artifact a client asked for: an investor report, a risk analysis, or the next brief of that kind. The knowledge is private. The artifact is the product.

The core is one Python process. Components call each other in-process through a public API. Apache Tika stays its own container, because it is a Java server. Postgres, and OpenSearch if retrieval uses it, stay their own containers because they are databases. The application deploys once.

A component is one reason the code changes. A pipeline step is not a component. If a small change has to touch several components, the boundary is wrong and the code moves. Each component exposes one public module. Other components import that module and leave the implementation alone.

## Components

### Ingestion

Changes when a source file comes out as different chunks.

Public API: `ingest(file) -> chunks`.

Inside: the Drive source, Tika, Unstructured, Docling, the hierarchical chunker, and the LlamaIndex metadata extractors (`document_title`, `section_summary`, `prev_section_summary`, `excerpt_keywords`, `questions_this_excerpt_can_answer`). Tables stay whole. Tika's text is not what gets chunked. Tika is called over HTTP at the container's `/rmeta` endpoint.

### Retrieval

Changes when a search comes back with different chunks. The agent uses this as a tool.

Public API: `save(chunks)` and `search(query, filters)`.

Inside: the SQL filters, the hybrid index (vectors plus BM25), and re-ranking. One Postgres schema holds the rows. OpenSearch, when used for fusing vector search with BM25, is private to this component. No other component writes its tables.

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

Ingestion may call `retrieval.save`. The agent may call `retrieval.search`, `oversight.approve`, and `oversight.record`. Retrieval and oversight call no other component. A guardrail sits on `produce` until those rules have their own owner. Evaluation and red-team runs live in the test suite and call the public APIs.

## Layout

```
ramonda/
  ingestion/
  retrieval/
  agent/
  oversight/
```

Only ingestion exists today, as the scripts at the repository root (`connect_drive.py`, `parse_tika.py`, `parse_unstructured.py`, `parse_docling.py`, `chunk.py`, `enrich.py`) and the Tika service in `docker-compose.yml`. Retrieval, agent, and oversight get a package when their first real code arrives. Empty packages are not part of the move.
