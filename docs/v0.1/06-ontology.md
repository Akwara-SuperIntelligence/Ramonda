# Ontology

The map is the live model of one company. The org chart organises it. This document says what the live HelixDB holds. It follows the [brief](01-product-brief.md), the [requirements](02-prd.md), the [simulator](03-demo-company.md), the [architecture](04-architecture.md), and [decision 19](07-decisions.md#19-build-the-map-from-the-systems-and-test-with-the-simulator).

Sales, shifts, payments, and other business rows are not in the map. Agents read them through the gateway from the system that holds them.

## Purpose

An agent needs the positions, the reporting lines, and the responsibilities. It needs to know which system holds a kind of record, and which position must approve a risky action. The live map stores those facts. OpenFGA decides access. The model does not.

## Positions, not people

A position is the stable object. A person fills a position for a stretch of time and then may leave. Links that grant access, responsibility, or approval attach to the position. They do not attach to the person.

The cafe positions, and who reports to whom, are the simulator's input in [03-demo-company.md](03-demo-company.md). HR will often store a messier title than the position name. The steward maps that title onto a position. A title string is not itself a grant of access.

## Responsibility and interest

A responsibility says what a position takes care of. Examples are a branch's sales and stock, the bakery, margin, or pay. An approval role says which position must decide before a class of write. Both are data on the map. The gateway enforces the approval. The agent reads the responsibility to decide who should hear about a change.

An always-on agent is woken by a schedule or by `{tenant}.changes`. It is not given a script that names the situation. It reads the change and the responsibilities, and it decides whether to raise the change and to which position. Memory of this company may inform that decision. Memory does not grant a permission and does not name an approver.

## The job layer

An agent belongs to one position. It has a manual that a person owns. The agent can read the manual through the gateway and cannot edit it. The stage is watch, then suggest, then act. The owner of the manual raises the stage. The agent cannot raise its own stage.

At watch, findings stay with the owner. At suggest, the positions named by the map are told, and a gated write stays pending. At act, routine work runs with nobody asking, and a gated write still waits for the approving position.

## What the live map holds

| Type | What an instance is |
| --- | --- |
| Position | A job on the org chart, such as branch manager for Westlands |
| Person | Someone who holds a position for a period. Not a key for access |
| Branch | A place that serves the public, or the bakery |
| Team | A group of positions, such as a branch team or head office |
| Product | An item the company sells or makes. Not a sale |
| Supplier | A company that supplies goods |
| Customer | A customer the company tracks, when the systems have one. Not a ticket |
| System | Odoo, the HR system, the payment log, the mailbox, or Keycloak. Says which system holds which kind of record |
| Responsibility | What a position takes care of |
| Agent | The agent for one position, with its stage |
| Manual | The human-owned instructions for that agent |
| Change | One accepted change to the map, with when it changed and why |

Links:

- `ReportsTo` connects a position to the position it reports to.
- `Holds` connects a person to a position for a period.
- `BelongsTo` connects an agent to a position.
- `ResponsibleFor` connects a position to the work it takes care of.
- `Approves` connects a position to the class of write it must decide.
- `RecordedIn` connects a kind of record to the system that holds it.

The steward may add a type when the systems require it. A hand-written file of instances is not the way those instances arrive.

## Where it lives

Two HelixDB databases sit on the client's stamp.

The staging database is the one Helix Foundry loads and refreshes. Foundry may overwrite it. Nothing reads staging to make an access decision.

The live database is the one the map steward writes. Only the steward updates it. OpenFGA is filled from this database. Agents reach it only through the gateway.

HelixDB stores a labelled property graph. The current quickstart does not require a schema file before a write. Whether an unknown label is rejected is [open question 2](#open-questions) below. Agents do not send writes. The steward does, for the live database. Foundry does, for the staging database.

The agreed Foundry install is self-hosted and may use any model, including a local one. The public introduction still describes the hosted product. See [the architecture](04-architecture.md#the-map) and [decision 12](07-decisions.md#12-foundry-sees-real-client-data-only-with-the-clients-approval).

## How the map is built and changed

1. The mirror copies the useful parts of Odoo, the HR system, Keycloak groups, and the payment log into one Postgres database. Email is not mirrored. Agents read the mailbox live through the gateway.
2. Foundry drafts types, cross-system links, and mappings from that Postgres database. The draft is versioned `ontology.toml` and `mappings.toml`, with provenance. Foundry loads the draft into staging.
3. The steward builds the org chart. It uses HR titles, manager fields, Keycloak groups, and how work flows. It merges messy titles onto positions. It adds responsibilities and approval roles, which Foundry does not know.
4. When the company has supplied an org chart, the steward compares it and flags differences.
5. The steward writes the checked result into the live HelixDB and records a change. The gateway then writes the OpenFGA tuples for that result. A request uses the previous pair or the new pair, never the new map with the old tuples.
6. Later changes arrive on `{tenant}.changes`. The steward applies an ordinary change itself. A large structural change sends the steward back to Foundry for a fresh draft, which the steward merges.
7. A person is asked only when sources disagree, or when the change is sensitive. That person holds the position for the decision. The live map stays as it was until they decide.

If the tuple write fails, the previous pair stays current. The gateway retries. It does not deny the whole company. The first failure is an audit row and an alert to the position that handles it.

Foundry's scheduled refresh writes staging only. It must not write the live HelixDB.

## How agents use it

An agent never opens HelixDB and never opens OpenFGA. It calls the gateway. The gateway takes the caller's token, asks OpenFGA, and only then reads the live map or the client system. A retrieval bug in Helix must not widen what OpenFGA refused.

A write is checked against the caller's position and against the approval role on the map. The agent does not apply the write itself.

## The Akwara Cafe map

The cafe map is an instance of the types above. The positions and places are listed in [03-demo-company.md](03-demo-company.md). The steward has to produce this shape from the systems the simulator filled, including HR titles that drifted. A correct map matches the simulator's hidden org chart. A matching file that a person typed does not count.

Customers appear when the systems have them. The cafe description does not require a loyalty list. Do not invent customers so the map looks full.

## Open questions

1. **Foundry and Redpanda.** Foundry refreshes staging on its own schedule. Its public docs do not show a subscription to `{tenant}.changes`. The steward listens to Redpanda. The steward asks Foundry for a new draft when the change is structural. Until that call is demonstrated, a Redpanda event updates the live map only through the steward, not through a Foundry refresh.
2. **Labels are not a compiled schema.** The HelixDB quickstart accepts a node label on write. It does not show a step that rejects an unknown type. Whether `ontology.toml` is the list of allowed labels is not decided.
