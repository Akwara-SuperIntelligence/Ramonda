# Own the interpreter, adopt the edges

No existing harness runs a fixed list of Steps. Every candidate assumes the model chooses the next tool, so the loop we would copy is the loop we do not want.

Decision: `pydantic-ai-slim` for the model port, tool schemas and OpenTelemetry spans; a ~250-line workflow interpreter we own; Procrastinate on PostgreSQL for durable Steps.

Rejected: LangGraph (the only first-class step graph, but it brings `langchain-core`, a graph defined in code while Workflows are data, and therefore a compiler); OpenAI Agents SDK (a 2,935-line model loop, sessions and telemetry on by default); Claude Agent SDK (a wrapper around a closed CLI).

**Consequence:** the interpreter is the audit boundary and must stay small enough to read in one sitting. The dependency is pinned and reached only through the model port, so an upstream API break is one file.
