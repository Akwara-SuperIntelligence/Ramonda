# Architecture, v0.1

Ramonda runs an enterprise's document workflows. It reads Documents, pulls out figures and statements, applies the enterprise's written Rules, and will not let a figure through unless a second Source confirms it. When two Sources disagree, the Run stops and a Person sees both values.

One product, many Tenants. Every Tenant has its own database, its own Roles, its own Workflows. A Workflow is data in that Tenant's Pack, so a new Tenant costs a Pack, not a fork.

## Shape

```
api        ──► modules ──► PostgreSQL
                                  ▲
worker     ──► modules ───────────┘        + Docling sidecar
connector  ──► modules ──► the Tenant's Sources
```

One image, three entrypoints, one database per Tenant, one parsing sidecar.

## Six modules

| Module | One reason to change | Owns |
|---|---|---|
| `documents` | how we read a Document | intake, parse, chunk, index, search, Anchor |
| `harness` | how a Workflow is executed | the loop, the seven verbs, the step budget |
| `rules` | how a Tenant's Rules are applied | Rule evaluation, Checks, Discrepancy |
| `work` | what a Run is | Run state, Artifact versions, Signatures, the review queue |
| `evidence` | what we must be able to prove | Evidence entries, hash chain, Explain |
| `access` | who may see what | Person, Role, Permission, Classification, Clearance |

Three dependency rules:

1. **`evidence` and `access` are leaves.** They depend on nothing else, so they can never grow an opinion about Runs or Documents.
2. **`rules` must not reach a model.** Only `harness` holds a model client. This is the whole of the determinism claim: a Rule evaluates, it does not reason.
3. **No upward edges.** `harness` composes and owns no data.

Enforcement in Python: one package per module, `modules/<name>/__init__.py` is the only public surface, and `import-linter` fails CI on any import deeper than another module's `__init__`. The compiler will not save you here, so the lint step is the compiler.

## Runtime

One image, three entrypoints:

- `api` serves the HTTP API. FastAPI.
- `worker` runs Runs, ingestion and Checks as jobs.
- `connector` polls or listens to one Source or one group of them.

Plus one Docling sidecar for parsing, and one PostgreSQL.

Why three: an API request must not block on a four-hundred-page scanned contract; the three scale on different axes; and a Connector fails for reasons the API should never share.

No message broker. Jobs are rows in PostgreSQL, managed by Procrastinate, claimed with `FOR UPDATE SKIP LOCKED`. That is enough for this size, and it removes a piece of infrastructure from a bank's network that nobody there wants to review.

A Run stops by setting `cancel_requested` on its row. The worker checks that flag at every Step boundary and before every model or tool call.

## Data

One database per Tenant. The same tables in every one.

`tenant_id` sits on every row even though each database holds one Tenant. A row that does not know its Tenant is a bug waiting for a bad restore, and the day a Tenant merges or splits, the column is the proof of what was whose.

Relational rows, vectors and keyword search live in one PostgreSQL. No search cluster: two stores meant two encoders for the same access rule, and they drifted.

Per-Tenant shape is data. `entities` columns are JSON, validated against that Pack's schema. A field becomes a real column only when three Packs need it or it appears in a hot filter.

## Access

Person → Role → Permission → Workflow.

Every request resolves the Person from a verified OIDC token, then checks one Permission. Every query is scoped to that Person's Tenant. There is no "admin sees all" path in code; a Permission with that meaning is still a Permission, held by a Role, in one Tenant.

Two identities never mix: a Person has a token from the Tenant's identity provider, and a Connector has a workload identity. A Connector never carries a Person's token.

v0.1 does not use database row-level security. It is a good second lock, and it arrives when a client's security review asks for it.

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

`GLOSSARY.md` for the words. `workflows.md` for what changes per Tenant. `pack.md` for what is in a Pack. `api.md` for the public surface. `releases.md` for how code reaches a Tenant. `harness.md` for the loop. `security.md` for what can go wrong. `evaluation.md` for how we know a Run is right. `docs/ADR.md` for the decisions that are hard to reverse.
