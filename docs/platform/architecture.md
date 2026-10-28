# Architecture, v0.1

Ramonda runs an enterprise's document workflows. It reads Documents, pulls out figures and statements, applies the enterprise's written Rules, and will not let a figure through unless a second Source confirms it. When two Sources disagree, the Run stops and a Person sees both values.

One product, many Tenants. Every Tenant has its own database, its own Roles, its own Workflows. A Workflow is data in that Tenant's Pack, so a new Tenant costs a Pack, not a fork.

## Shape

```
apps/api        ──► modules ──► PostgreSQL
                                     ▲
apps/worker     ──► modules ─────────┘        + Docling sidecar
apps/connector  ──► modules ──► the Tenant's Sources

modules/*       ──► kernel
```

One image, three entrypoints, one database per Tenant, one parsing sidecar. `apps/` is the composition root and imports anything. `kernel/` is plumbing and imports no Module.

## Six modules

| Module | One reason to change | Owns |
|---|---|---|
| `documents` | how we read a Document | intake, parse, chunk, index, search, Anchor |
| `harness` | how a Workflow is executed | the loop, the seven verbs, the context assembler |
| `rules` | how a Tenant's Rules are applied | Rule evaluation, Checks, Discrepancy |
| `work` | what a Run is | Run state, Artifact versions, Signatures, the review queue |
| `evidence` | what we must be able to prove | Evidence entries, hash chain, Explain |
| `access` | who may see what | Person, Role, Permission, Classification, Clearance |

`kernel/` is not a seventh Module. It holds the database base, the unit of work, settings, identifier generation and Trace setup: the plumbing every Module needs and none of them owns. It imports no Module and contains no domain word.

## The dependency graph

The whole architecture is this table. It is the only list of imports allowed between Modules.

| Node | May import |
|---|---|
| `apps/api`, `apps/worker`, `apps/connector` | any Module, and `kernel` |
| `harness` | `documents`, `rules`, `work`, `evidence`, `access` |
| `work` | `evidence`, `access` |
| `documents` | `access` |
| `rules` | — |
| `evidence` | — |
| `access` | — |
| `kernel` | — |

Three properties do the work:

1. **`rules`, `evidence` and `access` are leaves.** `rules` takes values and returns a verdict; it holds no database and no model, which is what makes a Rule signable. `evidence` and `access` depend on nothing, so they can never grow an opinion about Runs or Documents.
2. **`harness` is the only composer.** It calls every Module and owns no table. Only `apps/` imports `harness`.
3. **`documents` depends on `access`.** A search must drop Chunks above a Person's Clearance in SQL, not after it. That is why `access` is the shared vocabulary of who-may-see-what and not one module among six.

## What may cross a boundary

Data objects only: frozen dataclasses, `Protocol`s, enums and opaque identifiers. Never a table class, never a database session, never a query builder. A caller gets a snapshot of a value, not an object that can reach back into the Module's tables.

Modules also do not publish messages. A cross-Module action is a direct call into the other Module's `__init__.py`, the only form the linter can see. Work that must outlive a crash is a Procrastinate job, not an event bus.

## Enforcement

Six checks, blocking from the first commit. Python has no compiler to enforce a boundary, so these are the compiler:

1. `import-linter` carries one layered contract from the table above, plus forbidden edges: no Module imports `apps/`, nothing imports `harness` but `apps/`, `kernel` imports no Module.
2. A test asserts that the names each `__init__.py` exports match a committed allowlist. Adding a public name means editing the allowlist in the same diff, so a boundary change is a visible line.
3. A forbidden contract rejects `sqlalchemy`, `asyncpg` and `psycopg` inside any `__init__.py`.
4. A test asserts that SQL in `modules/<name>/` names only `<name>_*` tables.
5. A test asserts that only `apps/` opens a unit of work.
6. The OpenAPI drift check in [`api.md`](api.md).

## Runtime

One image, three entrypoints:

- `api` serves the HTTP API. FastAPI.
- `worker` runs Runs, ingestion and Checks as jobs.
- `connector` polls or listens to one Source or one group of them.

Plus one Docling sidecar for parsing, and one PostgreSQL.

Why three: an API request must not block on a four-hundred-page scanned contract; the three scale on different axes; and a Connector fails for reasons the API should never share.

No message broker. Jobs are rows in PostgreSQL, managed by Procrastinate, claimed with `FOR UPDATE SKIP LOCKED`. That is enough for this size, and it removes a piece of infrastructure from a bank's network that nobody there wants to review.

A Run stops by setting `cancel_requested` on its row. The worker checks that flag at every Step boundary and before every model or tool call.

## The audit pair is one transaction

Two Modules carry the audit trail: `work` holds the Run and the Signature, `evidence` holds the ledger. Whenever one write changes both, it is one transaction. That covers a Step commit (the Run advances, the assertion enters the ledger) and a Signature (the Signature is recorded, and the ledger gains it).

`apps/` opens one unit of work, `work` and `evidence` write inside it, and one commit ends it. Modules receive that unit of work, never a database session. This is the single exception to "no transaction spans two Modules", and it exists because the product claim is atomic: a figure is in the Artifact and in the ledger, or it is nowhere. Every other write touches one Module. `harness` owns no store: it calls two public APIs on the same unit of work.

## Data

One database per Tenant. The same tables in every one.

Each Module owns its tables, and the name carries the owner: `documents_chunk`, `work_run`, `evidence_entry`, `access_person`. One forward-only Alembic chain at the repository root collects every Module's metadata; a Module does not migrate itself. The prefix makes a cross-Module query visible in review and testable in CI.

Not in v0.1: a schema per Module, or a database user per Module. With one database per Tenant, the Tenant boundary already provides the isolation. A schema per Module is the answer when a security review asks for per-Module grants, not before.

`tenant_id` sits on every row even though each database holds one Tenant. A row that does not know its Tenant is a bug waiting for a bad restore, and the day a Tenant merges or splits, the column is the proof of what was whose.

Relational rows, vectors and keyword search live in one PostgreSQL. No search cluster: two stores meant two encoders for the same access rule, and they drifted.

Per-Tenant shape is data. `entities` columns are JSON, validated against that Pack's schema. A field becomes a real column only when three Packs need it or it appears in a hot filter.

## Access

Person → Role → Permission → Workflow.

Every request resolves the Person from a verified OIDC token, then checks one Permission. Every query is scoped to that Person's Tenant. There is no "admin sees all" path in code; a Permission with that meaning is still a Permission, held by a Role, in one Tenant.

Two identities never mix: a Person has a token from the Tenant's identity provider, and a Connector has a workload identity. A Connector never carries a Person's token.

v0.1 does not use database row-level security. It is a good second lock, and it arrives when a client's security review asks for it.

### Whose Clearance a Run uses

A Run acts as the Person who started it. That Person's Clearance is written into the Run row at start and does not change while the Run is in flight; a revoked Role blocks the next Run, not this one. The effective Clearance is the lower of that snapshot and the Workflow's classification ceiling, so a high-Clearance Person starting a low-Classification Workflow does not make the Run read more than the Workflow needs.

The snapshot is a fact in the Run row and appears in `Explain`. Reproducibility is the reason: the same Workflow version over the same Document version must produce the same Artifact, and a Clearance re-resolved at every Step makes that false and makes "why could it read page 9" unanswerable after the fact.

## Observability

Three layers, one join key (`run_id`):

| Layer | Holds | Retention |
|---|---|---|
| Evidence | what was asserted, from where, confirmed by which Source, signed by whom | permanent |
| Trace | every model call, verb, retrieval, token count, cost, duration | 90 days |
| Explain | the page that answers "why does this figure say 41" | as long as the Artifact |

Never put Traces in the ledger, and never put Evidence in logs. One is kept for years and is small; the other is kept for weeks and is large.

## What v0.1 is

One Tenant, one Workflow, end to end: Documents in, a Run, an Artifact, a Signature, Evidence out. One review page.

Not in v0.1: scheduling, bulk import, a second Tenant, self-service Pack editing, a fleet view.

**v0.2** adds Artifact change requests: a Person asks for a change, the engine runs again, and a new Artifact version arrives with a diff and the same Evidence trail. It also adopts the harness and onboards the second Tenant.

**v0.3** adds scheduling, Connectors at volume, exports, and a fleet view of which Tenant runs which version.

## Reading order

`GLOSSARY.md` for the words. `workflows.md` for what changes per Tenant. `pack.md` for what is in a Pack. `api.md` for the public surface. `releases.md` for how code reaches a Tenant. `harness.md` for the loop. `security.md` for what can go wrong. `evaluation.md` for how we know a Run is right. `docs/adr/ADR.md` for the decisions that are hard to reverse.
