# The module list

Status: accepted, revisable

Eleven modules, each a business capability every client needs, each named in plain language:

| Module | Owns |
|---|---|
| `identity` | accounts, sign-in, sessions |
| `access` | clearance — who may see which object |
| `sources` | Listeners, Source Adapters, change detection |
| `ingestion` | parse, chunk, enrich, store text |
| `search` | filter, keyword, vector, rerank |
| `evidence` | snapshots, candidate logs, citation binding |
| `ontology` | typed objects, links, holding area, promotion |
| `definitions` | rules and Procedure, sandboxed and hash-pinned |
| `artifacts` | document model, versions, suggestions, export |
| `jobs` | lifecycle, transitions, deadline, delivery |
| `agents` | skills, tool registry, context, runs |

Client-specific work — which adapters, which object types, which rules, which Procedure versions, which document structures, which skills — is configuration and client modules, never a change to these eleven.

The boundaries are expected to be wrong somewhere on the first attempt. The transcript's symptom applies: a small feature that forces edits in two modules means the boundary is misplaced, and the fix is to move the boundary.

## Consequences

- The two Codex workflows are not modules. They are one client's configuration over `definitions`, `artifacts` and `agents`.
- Every module must be extractable into its own service without rewriting its callers.
