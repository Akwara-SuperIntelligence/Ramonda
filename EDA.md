# EDA: always-on agents for organisations

Scope: how we run [Rakazo](https://github.com/elie222/rakazo) for many
organisations. We do not build the agent loop, the harness, memory, approvals,
computers, channels, identity, or billing. Rakazo has all of them. We build the
tenancy, provisioning, knowledge, and upgrade layers around an **unmodified**
Rakazo, and we run one stack per customer tier.

This document replaces an earlier one that specified a service we wrote and then
deleted. The argument is in [ACHITECTURE.md](ACHITECTURE.md); vocabulary follows
[GLOSSARY.md](GLOSSARY.md).

## 0. Decisions at a glance

| # | Decision | Choice | Why |
|---|---|---|---|
| 1 | Relationship to Rakazo | Consume released images; never vendor the source | Least maintenance; their CI builds six clients we would otherwise own |
| 2 | Packaging per stamp | Docker Compose, same images everywhere | Rakazo ships Compose; BYOC becomes one file |
| 3 | Organisation knowledge | Ours, exposed as an MCP server | Rakazo has bot memory, not organisation knowledge with provenance |
| 4 | Branding | Configure first (`RAKAZO_THEME`); patch later, few files | Brand is a customer requirement, not a starting one |
| 5 | Tenant to deployment | Customer is an Organisation; the isolation unit is a Space | Rakazo's row-level security and memory are Space-scoped |
| 6 | Model spend | The customer's own provider keys by default | No credit ledger of ours to reconcile |
| 7 | Control plane | Internal CLI and database, no UI | One customer does not justify a console |
| 8 | Moving an organisation between stamps | Not offered | Unverified by Rakazo, and expensive to build |
| 9 | Event streaming | None: Postgres, polling, and Rakazo's outbox | Two independent consumers is the threshold, and there are none |

## 1. The boundary

| Ours | Rakazo's |
|---|---|
| Stamp inventory, provisioning, version pins | The agent loop and turn execution |
| Organisation-to-stamp routing | Durable execution: lease, fence, recovery scan |
| Knowledge: ingestion, HelixDB, the MCP server | Memory: `MEMORY.md`, shared memory, memory providers |
| Egress allowlist (later) | Approvals, auto-review, spending limits |
| Per-stamp upgrade orchestration | Computers and sandbox providers |
| Fleet view and per-stamp health | Channels: Slack, email, messaging |
| Theme, domain, and signup policy per stamp | Identity: Better Auth, SCIM, passkeys |
| | Audit log, billing, evals |

One rule holds the line: **if a requirement can be met by configuration or by an
MCP tool, it is not our code.** Every line of ours is a line we maintain against
their releases.

Rakazo's own isolation unit is a **Space**. Their configuration guide states that
"each signed-in request sees only its Space's rows", and their memory guide that
"memory never crosses spaces". Our tenancy model therefore builds on Space, not
on the Organisation row.

## 2. Deployment profiles

One set of images, one Compose file, three topologies. Only `.env` changes.

| Profile | Customer | Isolation | Upgrade |
|---|---|---|---|
| **Shared cell** | Self-serve, SMB | Space-scoped RLS in one Postgres | One upgrade serves every customer |
| **Dedicated stamp** | Mid-market, regulated | Own Postgres, bucket, keys, host | One deployment, one window |
| **BYOC** | Banks, government | Customer's cloud and network | Customer applies a pinned release |

Rules:

- Every feature must work in all three profiles. A feature that only works in a
  cell couples the product to one business model.
- Shared cell is the default. A dedicated stamp is a paid tier, priced to fund
  fleet operations: many deployments mean many upgrades.
- Customisation is environment, theme, and the knowledge credential. Never a
  per-customer image.
- The test: deploy a whole stamp into a fresh account with one command and one
  config file. If that fails, isolation will not save the deal.

## 3. Stamps and the control plane

A **stamp** is one running Rakazo deployment. Its artifacts are small and fixed:

```
stamp/
  docker-compose.yml          pinned image tag, from upstream
  .env                        generated: secrets, domain, theme path, providers
  theme/theme.json            colours, fonts, radius
  knowledge.env               this stamp's knowledge endpoint and credential
```

The control plane is a CLI over a small database. It holds: stamp inventory,
organisation-to-stamp mapping, image tag per stamp, and the verified email
domains each organisation owns. It never holds customer content, model keys, or
conversation data. Creating a stamp writes the four files above, runs Compose and
the migration container, waits for health, and records the version.

## 4. Tenancy

Three words, three scopes:

- **Organisation** — one customer. Their people, their billing, their brand.
- **Space** — a team or project inside that customer. The isolation unit:
  row-level security, memory, and approval settings are keyed to it.
- **Stamp** — the deployment. Hard isolation between customers.

Rules:

- One Organisation per customer. Spaces for their teams. Memory never crosses a
  Space, so a customer who wants two separated bodies of knowledge gets two
  Spaces, not two Organisations.
- Rakazo derives identity from the session. We never pass a tenant ID into a
  request and never accept one from a client.
- Inside a cell, cross-customer separation is RLS plus one Space per customer
  team plus the knowledge credential. Our knowledge server accepts a credential,
  reads the tenant from it, and ignores any tenant named in the request.
- A dedicated stamp is required when a customer demands their own database, a
  named data-residency region, or a security review that will not accept shared
  tables.
- **Unverified:** whether Rakazo's Team Computer is scoped to a Space or to the
  whole Organisation. `computer-runtime.md` says "each workspace gets one Team
  Computer" and uses "workspace" loosely. Confirm before promising computer
  isolation between two Spaces on one stamp.

## 5. Knowledge

Rakazo has per-bot notes and per-space shared memory. It has no organisation
document store, no citations, and no tenant-partitioned vectors. That is ours.

```
documents ──▶ ingestion ──▶ HelixDB ──▶ retrieval ──▶ MCP server ──▶ agents
             (parse, chunk,   graph +    tenant filter   one tool,
              embed, dedupe)  vectors    and ranking     per-org credential
```

**The contract.** One MCP server, one tool, roughly `retrieve(query)`. It returns
compact results, each with a source and a score, capped in size. A document is
referenced, not inlined. A degraded answer carries a reason and a timeout; it
never hangs.

**Why MCP.** It is the one extension point in Rakazo that needs no patch: their
integrations screen accepts any HTTPS MCP server per Space, and connector
credentials are encrypted on the server and never returned by the API. One
connection per organisation, one credential per organisation.

**The limit, stated plainly.** The model decides when to call `retrieve`. There
is no harness-level rule that forces a retrieval before an answer. Citations
arrive as tool output, not as interface affordances. That is the price of not
forking, and it is acceptable until a customer pays for something better.

Ingestion owns the write path. Retrieval is read-only over HelixDB and is the
only reader. Deletion and forget remove nodes, edges, and vectors.

## 6. Identity and provisioning

Rakazo authenticates. We provision.

- `SIGNUPS_ENABLED`, `SIGNUP_ALLOWLIST`, and `SCIM_BEARER_TOKEN` are per stamp,
  set by the control plane: a customer's domain is allowlisted, or their
  identity provider provisions accounts over SCIM.
- Rakazo deliberately has no application admin role. `RAKAZO_ADMIN_EMAILS`
  covers plugin review, stdio MCP servers, and credit grants, and nothing else.
  A deployment-wide operator must therefore work outside their app, which is
  what the control plane is for.
- Our mapping is keyed on a verified email domain. Onboarding verifies the
  domain, then writes the allowlist entry into the right stamp.

## 7. Secrets, data, and egress

Rakazo already does more than we would have built:

- Connector, model, voice, memory, vault, and bot credentials are encrypted on
  the server and never returned by the API.
- Computers run restricted by default under Compose:
  `restrict-computer-egress.sh` blocks private ranges, the host, LAN, and cloud
  metadata endpoints.

What we must add or watch:

- **Disk encryption per stamp.** Rakazo stores transcripts and workspaces
  unencrypted under `DATA_DIR`, and its own documentation says that is
  unsuitable for a multi-tenant hosted install. A shared cell needs encrypted
  volumes; a dedicated stamp needs encrypted volumes and a documented key.
- **`PI_SESSION_RECORDING` stays off** in any cell.
- **No per-domain egress allowlist exists.** Restricted egress blocks internal
  targets; it does not restrict which public sites a computer reaches. Add a
  proxy only if a customer requires it.
- **Audit retention** defaults to 365 days (`AUDIT_EVENT_RETENTION_DAYS`) and the
  log forwards to a SIEM as JSON Lines. Per-customer retention is a stamp value.
- The control plane holds pointers only: no transcripts, no model keys, no
  secrets.

## 8. Event streaming

There is no bus. Rakazo is Postgres-only: a run is claimed by an atomic lease
and fence, scheduling is Graphile, delivery is its own outbox, and observability
is OpenTelemetry plus an append-only audit journal. We run no Kafka, no
Redpanda, and no Temporal, and no service of ours produces or consumes an event
log.

A bus is a strong answer to a question we do not have. Write the threshold down
so the next person does not rediscover it:

> **Add a bus when two independent consumers need the same event, at a volume
> Postgres polling cannot sustain. Until then, use what exists.**

The three cases that would reopen it, in the order they are likely to arrive:

| Case | What to do first | When a bus is justified |
|---|---|---|
| A customer wants facts in their warehouse near real time | Audit log export as JSON Lines, or `AUDIT_LOG_WEBHOOK_URL` to their SIEM. Both already exist. | Sub-minute, high-volume, replayable delivery to several consumers |
| Knowledge ingestion at volume | A queue table and a poller inside the knowledge service | One ingestion worker cannot keep up, and the backlog is measured |
| Fleet telemetry across many stamps | Push metrics to a time series store | Never for this case. A metrics pipeline is the correct tool |

Rules that follow:

- Ingestion state, retries, and dead letters live in Postgres. A broker is not
  how you get retries; a status column is.
- If a bus does arrive, it is one service with one contract, and it enters this
  document before any code exists.
- Reversal is expensive. A broker is an operational dependency on every stamp,
  BYOC included, and the customer has to run it. That cost is why the threshold
  is high.

## 9. Versioning and upgrades

- **Pin an image tag per stamp.** Never `edge`. Rakazo's released tags are the
  supported window.
- **Canary one stamp first.** A cell upgrade affects every tenant at once; a
  stamp upgrade affects one customer. Order them accordingly.
- **Migrations** run in Rakazo's own migrate container as the owner role, before
  the API starts. They are expand-and-contract because old and new processes run
  at once during a rollout.
- **Rollback** is the previous image tag plus a database restore. Test the
  restore drill once per stamp type, not once per customer.
- **Never patch the source.** If a customer requirement cannot be met by
  configuration or by an MCP tool, record it as a patch series of a few commits
  with a monthly rebase, and try to upstream it first. Their licence and
  contribution process allow it.

## 10. Failure modes

| Failure | Behaviour | Mitigation |
|---|---|---|
| Stamp upgrade fails | One customer degraded, others fine | Canary, previous tag, restore drill |
| Stamp lost | Its organisations lose service | Rebuild from Compose plus the last backup |
| Knowledge service down | `retrieve` returns degraded with a reason | Bounded timeout, run continues |
| Knowledge credential leaks | One tenant's documents exposed | Per-tenant credential, rotation, tenant from credential only |
| Postgres down on a cell | Every tenant on that cell stops | Health checks, restore drill, alert on lag |
| Model provider outage | A run fails and retries | Customer keys stay the customer's problem |
| Control plane down | No provisioning; running stamps unaffected | It is not on the request path |
| Customer needs their data out | Export or delete | Rakazo account export; verify scope first |

The control plane is deliberately off the serving path. If it stops, every
running stamp keeps working and only new provisioning waits.

## 11. Observability

Rakazo already emits run timings, structured logs, audit events, and queue
delays. We add the fleet view they do not have:

- Per stamp: image tag, health, organisation count, last backup, upgrade status.
- Across stamps: version spread, which stamp is behind, failed upgrades.
- Knowledge: p99 retrieval latency, citation rate, ingest backlog per tenant.

Alert on: two consecutive failed health checks, a stamp more than one minor
version behind, a backup older than its window, and knowledge latency above its
SLO.

## 12. Open questions

- Is the Team Computer scoped to a Space or to the Organisation? Confirm before
  promising computer isolation inside a cell.
- Can a whole Organisation move from a cell to a dedicated stamp? Account-level
  export and import exist; organisation-level migration is unverified. Until it
  is tested, sell the profile a customer starts on.
- Rakazo documents no per-organisation concurrency limit, and run admission does
  not set one. Enforce fair use by stamp sizing and provider quota, or build it.
- Should the egress allowlist be ours, or upstreamed as a Rakazo feature?
- Mobile branding: ship their store listings, or build our own Expo clients?
- When does a patch series beat a feature request upstream?

## 13. Dependencies

- **Every stamp:** Postgres, a container host or a sandbox provider, object
  storage, SMTP for account mail, a model provider, DNS and TLS.
- **Knowledge:** HelixDB, object storage for raw documents, an embedding model.
- **Control plane:** Postgres, DNS, the container host API.
- **Optional, per stamp:** Stripe if that customer buys credits, Axiom for logs,
  a memory provider.

## 14. Deliberately not built

The agent loop, the harness, tools, memory, approvals and auto-review, sandboxes,
channels, identity, audit, evals, billing, and the client applications. Rakazo
has them, their tests cover them, and their releases carry the security fixes.
