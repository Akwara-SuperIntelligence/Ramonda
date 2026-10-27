# Data model

There is no migration yet: this file is the schema record until the first vertical slice runs against a real database. One PostgreSQL database per Cell. Relational rows, vectors (`pgvector`) and keyword search live in the same database, so a filter and a search are one transaction. Table names are global; **one application schema version exists across all Cells**, while Pack versions vary per Tenant — the invariant that keeps reuse from becoming a fork.

`entities` columns are `jsonb`, validated against the Pack's JSON Schema on write. A field becomes a real column only when three or more Packs need it or it appears in a hot `WHERE` clause. See `adr/0002`.

## Documents

| Table | Key columns | Notes |
|---|---|---|
| `document` | `id`, `tenant_id`, `source_id`, `source_ref`, `classification`, `lifecycle`, `review_decision`, `entities` | `(source_id, source_ref)` is unique: identity comes from the Source, never the filename |
| `document_version` | `id`, `document_id`, `content_hash`, `received_at`, `parsed_at`, `superseded_at` | immutable; a citation names a `document_version`, never a `document` |
| `document_access` | `document_id`, `principal_id` | no rows means no one |
| `block` | `id`, `version_id`, `kind`, `ordinal`, `text`, `page` | one normalised shape for every format |
| `chunk` | `id`, `version_id`, `breadcrumb`, `text`, `anchor_section`, `anchor_paragraph`, `anchor_page`, `anchor_quote` | one Anchor per Chunk; `anchor_page` is null when the document has no printed pages |
| `chunk_embedding` | `chunk_id`, `vector` | `pgvector`; the tenant filter runs before the vector search |

## Work

| Table | Key columns | Notes |
|---|---|---|
| `subject` | `id`, `tenant_id`, `kind`, `external_refs` | the person or organisation a Case is about |
| `trigger` | `id`, `tenant_id`, `source_id`, `source_ref`, `payload`, `received_at` | an alert is a Trigger |
| `case` | `id`, `tenant_id`, `subject_id`, `pack_id`, `pack_version`, `state`, `decision`, `entities`, `opened_at`, `closed_at` | pins the Pack version it opened under |
| `case_trigger` | `case_id`, `trigger_id` | many-to-many from day one, so merging cases is not a migration |
| `case_event` | `id`, `case_id`, `kind`, `payload`, `actor`, `at` | state transitions, append-only |
| `rule_evaluation` | `id`, `case_id`, `rule_id`, `pack_version`, `outcome`, `inputs_hash`, `at` | what fired, under which rule version |
| `check_result` | `id`, `case_id`, `check_id`, `claim`, `status`, `values`, `at` | `status`: `confirmed`, `discrepancy`, `missing` |
| `decision_signature` | `id`, `case_id`, `principal_id`, `decision`, `pack_version`, `at` | a person's signature; the only thing that closes a Case |

## Evidence

| Table | Key columns | Notes |
|---|---|---|
| `evidence` | `id`, `cell_seq`, `prev_hash`, `hash`, `kind`, `payload`, `case_id` (nullable), `at` | append-only; no `UPDATE` or `DELETE` grant for the application role |
| `evidence_checkpoint` | `id`, `upto_seq`, `hash`, `signature`, `at` | Ed25519 checkpoint, written periodically |
| `pack_install` | `id`, `pack_id`, `version`, `signature`, `installed_at`, `status` | an install that fails replay is rejected |
| `idempotency_key` | `key`, `request_hash`, `response`, `expires_at` | write endpoints only |

`evidence.kind` is one of `NumberAsserted`, `SourceConfirmed`, `RuleEvaluated`, `CheckFailed`, `HumanSigned`, `PackInstalled`. Every row carries the hash of its payload and the previous row's hash, so a single edited row breaks the chain.

## Invariants a reviewer should check in a migration

1. No table carries a per-client column. Client shape lives in `entities`.
2. Every query that returns a Document or a Chunk filters by Classification and Clearance **and** by Tenant, in one place.
3. `evidence` has no update or delete path in code or in grants.
4. `case.pack_version` is written once, at open.
5. Nothing but `rules` can write `check_result`.
6. A `Decision` row requires a `check_result` in `confirmed` state and a `decision_signature`.
