# Architecture

Ramonda is one product. It reads an enterprise's documents and systems, assembles a Case, applies the enterprise's written rules, and stops when a Claim is not confirmed by two independent Sources. It is a modular monolith: six modules with enforced boundaries, one deployment unit per process, one PostgreSQL database per Cell.

The bank anti-money-laundering case is the reference case, not a special build. It is chosen because it is the hardest: many Sources, deterministic rules, two-source Checks, human stops, and a regulator who asks why.

## Shape

```
                    agent                     ← the only module that may call a model
        ┌────────────┼─────────────┐
     corpus        rules          case
        │            │              │
        └────────────┴──────┬───────┘
                     evidence             ← a leaf
                     identity             ← a leaf
```

**Six modules**, each with one reason to change:

| Module | Reason it changes | Owns |
|---|---|---|
| `corpus` | how we read documents | intake, parse, chunk, index, search, citation |
| `agent` | how a use case reasons | plan, gather, extract, draft, escalate |
| `rules` | how the client's rules are applied | rule evaluation, Checks, `Verified` |
| `case` | what a piece of work is | Case state, Triggers, review queue, signed Decision |
| `evidence` | what we must be able to prove | Evidence entries, hash chain, regulator bundle |
| `identity` | who may see what | Tenant, Principal, Classification, Clearance |

There are no library crates yet. Packs, model providers and storage arrive as modules when they have a caller — a library with no dependency is an unfinished thought, not architecture.

## Three dependency rules

1. **`evidence` and `identity` are leaves.** They depend on nothing in the workspace, so they can never grow an opinion about Cases or Documents.
2. **`rules` must not reach a model.** No module may name a model provider except `agent`. This is the whole of the determinism claim, and `scripts/check-boundaries.sh` fails the build on a violation.
3. **No upward edges.** `agent` sits at the top and composes; it owns no data.

`scripts/check-boundaries.sh` reads the manifests and fails on a forbidden edge. It is fifteen lines of bash on purpose: the rule is small, and a checker you cannot run is worse than no checker.

## Runtime, per Cell

The target is three processes from one workspace — `api`, `worker`, `connector` — plus a Docling sidecar. They land with the first vertical slice; the decision is recorded in `adr/0008`. Domains stay logical; only the runtime shape splits.

## Data, per Cell

One PostgreSQL database holds relational rows, vectors (`pgvector`) and keyword search. There is no search cluster: two stores meant two policy encoders, which is how the previous system drifted. See `adr/0002`.

## Reuse

To serve a second enterprise, we deploy one new Cell and write one new Pack. The modules do not change. A Source we cannot yet read costs one new Connector in this repository, never a fork. See `adr/0001`.

## Reading order

`GLOSSARY.md` for the words, `modules.md` for the boundaries, `adr/` for why, `pack-spec.md` for what changes per client, `data-model.md` for the tables, `api-conventions.md` for the contract, `runbook-new-client.md` for the day a new client arrives.
