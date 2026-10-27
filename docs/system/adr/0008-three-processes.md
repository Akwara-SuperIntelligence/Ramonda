# Three processes per Cell, one workspace

A Cell runs `api`, `worker` and `connector` from one workspace, plus a Docling sidecar. `api` serves the public API; `worker` runs ingestion, Checks and drafting as durable jobs on `apalis` over PostgreSQL; `connector` polls one external Source.

Reason: a four-hundred-page scanned contract must not block an analyst's request, and the three have different scaling curves — `api` scales with people, `worker` with documents, `connector` with Sources. Splitting by runtime characteristic is not splitting by domain: all three link the same six modules, hold no business logic, and are wired in their `main.rs` only.

Job durability is `apalis` on the same PostgreSQL database: transactional enqueue, `FOR UPDATE SKIP LOCKED`, retries, idempotent handlers. Temporal was considered — its Rust SDK reached GA in September 2026 — and rejected for now because a sovereign Cell would need a Temporal server, a second database and a UI inside the client's perimeter. Revisit at the first saga that needs compensation.
