# Decisions

Twelve decisions became sixteen as boundaries were pinned down. Each one would be expensive to reverse, or a reader would question it without context. Each one names the alternative it rejected.

| # | Decision |
|---|---|
| [1](#1-one-product-many-tenants-no-forks) | One product, many Tenants, no forks |
| [2](#2-one-database-per-tenant) | One database per Tenant |
| [3](#3-six-modules-python-fastapi) | Six modules, Python, FastAPI |
| [4](#4-workflows-are-data-owned-by-one-tenant) | Workflows are data, owned by one Tenant |
| [5](#5-rules-are-data-and-cannot-reach-a-model) | Rules are data and cannot reach a model |
| [6](#6-a-check-needs-two-source-classes-and-stops-on-disagreement) | A Check needs two Source classes and stops on disagreement |
| [7](#7-evidence-is-permanent-traces-expire) | Evidence is permanent, Traces expire |
| [8](#8-own-the-interpreter-adopt-the-edges) | Own the interpreter, adopt the edges |
| [9](#9-one-image-pinned-per-tenant-expand-then-contract) | One image, pinned per Tenant, expand then contract |
| [10](#10-one-copy-of-the-system-per-tenant) | One copy of the system per Tenant — **provisional** |
| [11](#11-documents-are-hostile-input) | Documents are hostile input |
| [12](#12-authentication-is-a-per-tenant-oidc-boundary) | Authentication is a per-Tenant OIDC boundary |
| [13](#13-boundaries-are-a-graph-and-only-a-graph) | Boundaries are a graph, and only a graph |
| [14](#14-a-kernel-holds-the-plumbing) | A kernel holds the plumbing |
| [15](#15-the-audit-pair-is-one-transaction) | The audit pair is one transaction |
| [16](#16-a-run-acts-as-the-person-who-started-it) | A Run acts as the Person who started it |

---

## 1. One product, many Tenants, no forks

Every client is served by this repository. What differs per client lives in that Tenant's Pack. We never fork the repository, never copy a module into a client variant, and never keep a branch per client.

Reason: a fork means each client's repository knows only its own security fixes, and the fifth client costs as much as the first.

**Consequence:** a difference that cannot be expressed as data is a design bug in the platform, not a client request. Fix the model for everyone and test it with the second Tenant.

---

## 2. One database per Tenant

Each Tenant gets its own PostgreSQL database, holding relational rows, vectors and keyword search. Every database has the same tables.

`tenant_id` still sits on every row, although the database holds one Tenant. A row that does not know its Tenant is a bug waiting for a bad restore, and merges or splits need the column as proof of what was whose.

Rejected: a shared database with `tenant_id` only (cheaper, but a bank's review becomes an audit of every query); a schema per Tenant in one database (migrations run N times, and isolation does not improve).

Each Module owns its tables and the name carries the owner: `documents_chunk`, `work_run`, `evidence_entry`, `access_person`. One forward-only Alembic chain at the repository root collects every Module's metadata.

Rejected: a schema per Module and a database user per Module. With one database per Tenant the Tenant boundary already isolates, and a table prefix plus a CI test buys most of what a schema buys. It is the answer when a security review asks for per-Module grants, not before.

**Consequence:** a fleet of databases, each with its own backup, restore and migration run.

---

## 3. Six modules, Python, FastAPI

One modular monolith: `documents`, `harness`, `rules`, `work`, `evidence`, `access`. One package per module, one public `__init__.py` per module, and `import-linter` in CI rejecting any import deeper than another module's `__init__`.

Rejected: Rust. It was the previous plan and it was reversed. Document AI, parsing and evaluation tooling are Python, the team is small, and the compiler was buying correctness we can buy three cheaper ways: one function that builds a `Verified` value, one function that scopes a query to a Tenant, and one lint step that enforces the module graph.

**Consequence:** the type-level guarantee becomes a runtime check plus a test. The lint step becomes the compiler, and it must never be skipped. The graph the six Modules form, and the imports allowed between them, is [13](#13-boundaries-are-a-graph-and-only-a-graph).

---

## 4. Workflows are data, owned by one Tenant

A Workflow is an ordered list of Steps in the Tenant's Pack. Each Step names one verb from a fixed set of seven and gives it inputs. There is no loop, no conditional and no sub-Workflow.

A Workflow belongs to exactly one Tenant. There is no shared library, no base Workflow, no inheritance and no registry. Two banks may both run a "taxes" Workflow; they are two files that started from the same copy. **Copy, never share.**

Rejected: code per client (that is a fork by another name); a shared definition that several Tenants reference (one change must then satisfy two compliance teams and two change-control processes); a general DSL with branching.

**Consequence:** a fix to one Tenant's Workflow does not reach the others. That is the price of independence and it is paid on purpose.

---

## 5. Rules are data and cannot reach a model

A Rule is YAML in the Pack: typed operators, no loops, no recursion, no user-defined functions. `rules` imports nothing: no database, no model. It takes values and returns a verdict, which is what lets a compliance officer read it without seeing the rest of the system.

Reason: "the company's own written rules, exactly as defined" is a legal claim. A compliance officer must be able to read a Rule, sign it, and see later the exact Rule version that produced an Artifact. A rule that has to be executed to be understood cannot be signed.

**Consequence:** any behaviour that needs judgement belongs in `extract` or `draft`, and its output must carry an Anchor and pass a Check before it can reach an Artifact.

---

## 6. A Check needs two Source classes and stops on disagreement

A Check compares a Claim across at least two Sources from **different Source classes**. A Source class groups Sources that share one upstream, so a vendor and its reseller cannot confirm each other, and a manual search of the same vendor cannot confirm it either.

The Check compares the Claim, not the raw number: both Sources must answer true or both false. Where the Tenant requires equality, the Check declares it and the values must be equal after the declared unit conversion.

If the Sources do not confirm, the Run **stops**. Both values and both Anchors go to a Person. There is no tolerance and no Source precedence: a tolerance guesses, and precedence hides a disagreement.

**Consequence:** stopping is a success case, not an error. It is the product.

---

## 7. Evidence is permanent, Traces expire

Two records, never one.

**Evidence** is the append-only, hash-chained record of every assertion, its Anchor, the Source that confirmed it, the Rule version and the Signature. It is kept for years.

**Trace** is the operational record of a Run: every model call, verb, retrieval, token count and duration. It is kept 90 days and then dropped.

They join on `run_id`, and every Evidence row carries the `trace_id` that produced it.

Rejected: one store for both (either a ledger too large to retain or a trace store too weak to audit); logs as the audit trail (logs may be dropped, and are for operators).

**Consequence:** a Person can always answer "why does this figure say 41", and the answer survives the Trace.

---

## 8. Own the interpreter, adopt the edges

No existing harness runs a fixed list of Steps. Every candidate assumes the model chooses the next tool, so the loop we would copy is the loop we do not want.

Decision: `pydantic-ai-slim` for the model port, tool schemas and OpenTelemetry spans; a ~250-line workflow interpreter we own; Procrastinate on PostgreSQL for durable Steps.

Rejected: LangGraph (the only first-class step graph, but it brings `langchain-core`, a graph defined in code while Workflows are data, and therefore a compiler); OpenAI Agents SDK (a 2,935-line model loop, sessions and telemetry on by default); Claude Agent SDK (a wrapper around a closed CLI).

**Consequence:** the interpreter is the audit boundary and must stay small enough to read in one sitting. The dependency is pinned and reached only through the model port, so an upstream API break is one file.

---

## 9. One image, pinned per Tenant, expand then contract

One image with three entrypoints (`api`, `worker`, `connector`). Each Tenant pins an image digest. Code, schema and Pack version independently: `0.1.x`, numbered migrations, and per-Tenant semver.

Migrations are forward-only and every one must be safe while the previous image is still running. A destructive change takes three releases: add, switch, drop. Rolling back means pinning the old digest, and the schema stays where it is.

No control plane in v0.1: a pinned `deployment.yaml` per Tenant and a script.

**Consequence:** a rollback never requires a migration rollback, which is the only reason rollbacks stay boring.

---

## 10. One copy of the system per Tenant

**Status: provisional.**

A Tenant gets one running copy: one compose project, one database, one set of processes. Not one copy holding several Tenants.

Reason: it matches one database per Tenant, it makes a bank's security review a single diagram, and it makes isolation a fact rather than a filter.

**Trade-off:** a "unified interface" across Tenants is then one UI over several copies, or an aggregation later. That is cheaper than getting the isolation story wrong once.

This reverses if a Tenant turns out to be many organisations under one brand, or if a pilot needs two clients in one copy before they can afford their own. Both would be resolved by Tenancy above Tenant, not by sharing a database.

---

## 11. Documents are hostile input

Every Document is untrusted. It can contain hidden text, white-on-white instructions, a prompt injection in a table cell, or a sentence designed to make the model skip a Check.

Controls, in order of importance:

1. A Document never reaches a path that can change the Workflow, the Rules, the Permissions or the prompt.
2. The model only ever sees delimited, labelled content, and is told that content is data.
3. Every extracted value carries an Anchor, and no value reaches an Artifact without a Check.
4. No tool call, no Source fetch and no escalation is derived from Document text.
5. A Document may produce a Discrepancy, never an exception to the Checks.

**Consequence:** features that let a model decide what to do next are out of scope, permanently.

---

## 12. Authentication is a per-Tenant OIDC boundary

The core understands one thing: a verified OIDC token carrying Tenant, Person, Roles and Clearance. Anything else is configuration.

Default is a cell-local Keycloak, with the customer's own IdP brokered in where they have one, and a break-glass local admin so the system stays operable when their IdP breaks. A managed broker is allowed only where the Tenant accepts processing outside its region; the US-only brokers were rejected on residency, not on price.

Connectors use a workload identity, one per Connector, never a Person's token. Upstream credentials live in the Tenant's own sealed store, never in the Pack and never in the identity provider.

**Consequence:** no vendor SDK in the core, a JWKS per Tenant, and moving a Tenant to a different IdP is a configuration change.

---

## 13. Boundaries are a graph, and only a graph

`architecture.md` holds one table: what each Module may import. `import-linter` reads it. `rules`, `evidence` and `access` are leaves. `harness` calls every Module and owns no table. Nothing points up: no Module imports `apps/`, nothing imports `harness` but `apps/`, and `kernel` imports no Module.

A Module's public surface carries data objects only: frozen dataclasses, `Protocol`s, enums, opaque identifiers. Never a table class, never a database session, never a query builder. A caller gets a snapshot of a value and cannot reach back into the Module's tables.

Modules do not publish messages. A cross-Module action is a direct call, because an in-process bus is an edge the linter cannot see.

Rejected: an in-process event bus (flexible, but half the graph becomes invisible and the table stops being the architecture); returning entities (one database, so it works, until the first lazy load reaches across two Modules' tables); a schema per Module (see [2](#2-one-database-per-tenant)).

**Consequence:** the gain is change locality, not a migration to services later. Extractability survives only as two cheap invariants: no Module reads another Module's tables, and no transaction spans two Modules except the audit pair in [15](#15-the-audit-pair-is-one-transaction). A boundary that turns out wrong is a refactor in one repository, and the linter is the review.

---

## 14. A kernel holds the plumbing

`kernel/` holds the database base, the unit of work, settings, identifier generation and Trace setup. Every Module may import it. It imports no Module and contains no domain word: no Run, no Document, no Artifact.

Rejected: plumbing inside `access` or `work` (either would stop being a leaf); plumbing copied into each Module (six ways to open a session and six ways to make an identifier).

**Consequence:** it is called `kernel` and not `core` or `shared`, because those names collect unfinished domain logic. The import-linter contract treats it as a node with no outgoing edges, and a domain noun in it belongs to a Module.

---

## 15. The audit pair is one transaction

A write that changes both `work` and `evidence` commits once. That is every Step commit (the Run advances, the assertion enters the ledger) and every Signature (the Signature is recorded, and the ledger gains it).

`apps/` opens one unit of work, `work` and `evidence` write inside it, and one commit ends it. `harness` owns no store: it calls two public APIs on the same unit of work.

Rejected: two commits with a repair job (a window where the Run is ahead of the ledger, and the repair job is the thing an auditor asks to see fail); Evidence first and the Run second (a crash leaves an assertion for a Step that never committed, and `Explain` can then show a claim the Artifact does not contain).

**Consequence:** this is the only cross-Module transaction in the system; every other write touches one Module. Only `apps/` opens a unit of work, and a CI test asserts that.

---

## 16. A Run acts as the Person who started it

The Run row records that Person and the Clearance held at start. The Run keeps that Clearance until it ends, and effective Clearance is the lower of the snapshot and the Workflow's classification ceiling.

Rejected: re-resolving the Person at every Step (a revoked Role would stop a Run mid-way, but the same Workflow version over the same Document version would stop producing the same Artifact, and "why could it read page 9" becomes unanswerable after the fact); a Run identity declared in the Pack (a second identity system beside the Person, for nothing the snapshot does not already give).

**Consequence:** revocation is a policy, not a mechanism. A Tenant that wants an in-flight Run stopped gets a flag checked at each Step boundary, the same shape as `cancel_requested`.
