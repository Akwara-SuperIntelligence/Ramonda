# Evidence is permanent, Traces expire

Two records, never one. **Evidence** is the append-only, hash-chained record of every assertion, its Anchor, the Source that confirmed it, the Rule version and the Signature. It is kept for years. **Trace** is the operational record of a Run: every model call, verb, retrieval, token count and duration. It is kept 90 days and then dropped.

They join on `run_id`, and every Evidence row carries the `trace_id` that produced it.

Rejected: one store for both (either a ledger too large to retain or a trace store too weak to audit); logs as the audit trail (logs may be dropped, and are for operators).

**Consequence:** a Person can always answer "why does this figure say 41", and the answer survives the Trace.
