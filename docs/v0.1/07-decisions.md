# Decisions

This log is why a choice was made. A client auditor, or a new engineer, should be able to see the decision, what we refused, and where the argument lives. It records choices already made in the [brief](01-product-brief.md), the [requirements](02-prd.md), the [architecture](04-architecture.md), the [security model](05-security-model.md), and the [ontology](06-ontology.md). It does not add new ones.

To add a decision, append the next number. To change one, add a new entry and mark the old entry **Superseded by N**. Do not delete or rewrite the old text.

## 1. Consume Rakazo unmodified

**Decision.** Rakazo is the agent runtime, the chat, and the staff web and mobile clients. We pin a release. We do not fork it and we do not patch it (R33).

**Options turned down.** A harness we write. A fork so we can change login or approvals.

**Why.** The loop, the clients, and the harness are mature. Our difference is the map, the gateway, and the connectors. A fork would be ours to rebase.

**What it costs us.** If a release cannot do something we need, we stop and record the gap. We do not patch our way through it.

**Where it's argued.** [Brief, How it is built](01-product-brief.md#how-it-is-built). [Architecture, Agent runtime](04-architecture.md#agent-runtime).

## 2. Redpanda from the start

**Decision.** Events and audit run on Redpanda from the start (R15). Postgres commits an action and its event in one transaction. A relay publishes the committed outbox row. The connector call uses an idempotency key. If the gateway dies after the client system has applied a write, it retries that approved action with the same key. It does not retry an action that is still waiting for a person (R16).

**Options turned down.** Postgres only, with a bus added later. Debezium in the Akwara Cafe demo.

**Why.** The audit stream, the watcher, standing agents, schedules, and artifact lineage all need the same facts. Two writes, one to Postgres and one to the bus, can lose one of them. The outbox is the handoff, not a temporary bus. Debezium can replace the relay later. The outbox table is the contract. A Connect cluster is more process than the demo needs.

**What it costs us.** Every stamp runs Redpanda, including one café. We own a small relay.

**Where it's argued.** [Architecture, Events](04-architecture.md#events).

## 3. The map goes live only after a person approves it

**Decision.** HelixDB stores the approved map (R1, R3). Helix Foundry drafts a version. Versions do not change. Nothing in the live database changes until Nelly Achieng approves it. In Foundry that step is Make current. An automatic Foundry load must not write this stamp's live HelixDB. A refresh that would change who owns something, who cares, a role, who may read a type, or who is accountable stays a proposal.

**Options turned down.** Hand-building every node. Letting Foundry's scheduled refresh write the live graph. Treating a draft as the map staff rely on.

**Why.** A model must not publish the map by itself. Foundry does not write back to client systems, and it does not know our permissions.

**What it costs us.** A new owner or a new supplier is not in the map until a person approves a version. Sales and deliveries are not delayed by that. They are read from the client system when the agent asks.

**Where it's argued.** [Ontology, How the map is built and changed](06-ontology.md#how-the-map-is-built-and-changed). [Architecture, The map](04-architecture.md#the-map).

## 4. Permissions switch with the map, as one pair

**Decision.** OpenFGA tuples are rebuilt only from an approved map (R3, R7). A request uses one pair: a map version and the tuples written from that version. The gateway switches only after the new tuples commit. If that write fails, the previous pair stays current. The new Helix load is not served. There is no extra grace period after the new tuples commit.

**Options turned down.** Letting the model grant access. Serving the new map while the old tuples are still in force. A tenant column instead of a real switch.

**Why.** A retrieval bug in Helix must not widen what OpenFGA refused. A half-updated pair would do that.

**What it costs us.** Access the new map would remove stays in force until the new tuples commit. Nelly is alerted on the first failure. The gateway retries. It does not lock the whole company.

**Where it's argued.** [Ontology, How the map is built and changed](06-ontology.md#how-the-map-is-built-and-changed). [Security model, Identity and access](05-security-model.md#identity-and-access).

## 5. Agents notice. They are not scripted per scenario

**Decision.** An always-on agent is woken by `{tenant}.changes` and decides what matters (R20). Who would care is read from the map: `Owns` and `CaresAbout`. Amina owns Westlands. Waste cost matters to her and to Grace. Memory may inform the decision. It does not grant authority. `{tenant}.triggers` is only for schedules and outside webhooks.

**Options turned down.** A hand-written rule per scenario, such as a waste threshold that raises the alert itself.

**Why.** A script per situation does not survive the next company. The map already says who is responsible.

**What it costs us.** The agent can miss something, or raise something a person would have filtered. That is a judgement, not a permission.

**Where it's argued.** [Architecture, Agent runtime](04-architecture.md#agent-runtime). [Ontology, Responsibility and interest](06-ontology.md#responsibility-and-interest).

## 6. One identity per standing agent

**Decision.** Each standing agent is one principal, like a new hire, not one identity per scenario (R8). The Akwara ops agent has a role, explicit limits, and a named human manager. When nobody asked, the gateway acts as that agent. It never uses a shared credential. It may read within its role. It may take a small reversible step that does not change a client system, such as drafting a note. It asks a human when it is unsure, when the step is irreversible, or when the step is outside its role. A write to a client system still follows the approval rules (R12, R14). The audit row names the agent and the accountable human. When a person asked, the gateway acts as that person.

**Options turned down.** A shared service login. A fresh identity invented for each event.

**Why.** An auditor has to see who acted. A shared password hides that.

**What it costs us.** Every standing agent needs a principal, limits, and a named manager before it runs.

**Where it's argued.** [Architecture, Agent runtime](04-architecture.md#agent-runtime). [Security model, Identity and access](05-security-model.md#identity-and-access).

## 7. The watcher records and alerts. A human pauses

**Decision.** The watcher reads `{tenant}.audit` and `{tenant}.changes` (R18). It may record a finding and alert the client admin. For Akwara Cafe that person is Nelly, including when a change suggests the map is behind, such as a new manager, branch, or supplier. It cannot stop a run, pause an agent, edit the map, or write tuples. Pause is a control on the admin console. A human uses it (R32).

**Options turned down.** A watcher that blocks a later action, or that applies a map change itself.

**Why.** A second model must not be able to change the books or the map. A person makes that call.

**What it costs us.** A bad run continues until a person pauses it. A pause does not undo a write the client system already accepted.

**Where it's argued.** [Architecture, Audit](04-architecture.md#audit). [Ontology, How the map is built and changed](06-ontology.md#how-the-map-is-built-and-changed). [PRD, R18](02-prd.md#audit-and-events) and [R32](02-prd.md#admin-console).

## 8. The gateway learns who is calling from its own OAuth token

**Decision.** Rakazo v0.9.0 does not forward the signed-in user's session or ID token to MCP servers. The gateway is a remote MCP server. Its OAuth authorization server is Keycloak, or the client's Entra ID or Okta. A staff member who is already signed in consents once. The gateway then receives a token for that person and acts as them (R6, R8). The standing agent has its own client and its own token. The gateway ignores a tenant or user id written in a tool argument.

**Options turned down.** Forking Rakazo so it passes the session through. Trusting a user id in the tool call.

**Why.** The documented release has separate auth for each MCP server. We use that, instead of a patch.

**What it costs us.** Each person, and each standing agent, must consent to the gateway. We have not yet shown that Keycloak completes that flow with Rakazo v0.9.0. Until that run works, this decision is specified, not demonstrated.

**Where it's argued.** [Architecture, MCP gateway](04-architecture.md#mcp-gateway) and [Identity](04-architecture.md#identity). [Security model, Identity and access](05-security-model.md#identity-and-access).

## 9. Ramonda's approval step is the one that counts

**Decision.** A write that changes a client system returns pending until the approver named by the rule decides in Ramonda's own approval step (R12, R13). The gateway stores that decision. That row is the audit record. The approver can take the step from the staff app, including on a phone (R19). A Rakazo approval card alone does not release the write. Rakazo does not send the card to the gateway. An artifact version needs its own approval. Approval of an earlier version does not cover a later one (R24, R27). A decline writes nothing and is still audited.

**Options turned down.** Treating Rakazo's Allow once, Always, or Deny as the record. Letting the model approve itself.

**Why.** An auditor has to find the decision in our log. Rakazo's card never arrives there.

**What it costs us.** The approver uses Ramonda's step, not only the card Rakazo may also show.

**Where it's argued.** [PRD, Approvals](02-prd.md#approvals) and [App and notifications](02-prd.md#app-and-notifications). [Architecture, MCP gateway](04-architecture.md#mcp-gateway).

## 10. One stamp per client

**Decision.** One client is one deployment: its own Rakazo, Postgres, HelixDB, OpenFGA store, OpenBao path, and Redpanda (R36). Topics use that tenant's prefix. Akwara Cafe's prefix is `akwara-cafe`. A second client is a second stamp of the same images, not a tenant column in a shared database. Inside the stamp, people are separated by OpenFGA.

**Options turned down.** One database for many clients, with a tenant filter on every query.

**Why.** A missed filter would fail R36. Enterprises will audit this.

**What it costs us.** Every client pays for a full stamp, including the one-café demo. The demo cannot show a cross-tenant read until a second stamp exists.

**Where it's argued.** [Architecture, Tenancy and isolation](04-architecture.md#tenancy-and-isolation). [Security model, Tenant isolation](05-security-model.md#tenant-isolation).

## 11. A job is not the same link as access

**Decision.** `HasRole` is the job. `MayRead` is permission to read a type. David's job is finance analyst. His access to margins is `MayRead` on `BranchMargin`. They are not one link.

**Options turned down.** One link that means both "this is their job" and "they may read this type".

**Why.** A job title must not silently grant every field that job might see. Margin and pay are their own object types so OpenFGA can hide them.

**What it costs us.** The pack has two link types where one might have seemed enough. The names are the ones in the ontology. A rename would be a new entry here, not an edit of this one.

**Where it's argued.** [Ontology, The Akwara Cafe map](06-ontology.md#the-akwara-cafe-map).

## 12. Foundry sees real client data only with the client's approval

**Decision.** Helix Foundry, by default, sends synced tables and up to five documents per set to Anthropic models hosted through Helix. A Pro or Max workspace can use its own Anthropic key instead. Foundry may run on a client's real data only with that client's own model key, or a provider the client approved in writing. Until then it drafts from Akwara Cafe's fake data only.

**Options turned down.** Pointing Foundry at a real client's Odoo or HR data while the hosted default model is still in use.

**Why.** That path is not the Ramonda agent's provider, which is still unset. The client's contract has to cover it.

**What it costs us.** A real client's map cannot be drafted in Foundry until the key or the written approval is in place. The demo is not blocked. Its data is fictional.

**Where it's argued.** [Security model, Threats](05-security-model.md#threats) and [Data handling](05-security-model.md#data-handling). [Ontology, Where it lives](06-ontology.md#where-it-lives).

## 13. Assemble what is mature. Build only what is different

**Decision.** We assemble Rakazo, HelixDB, Helix Foundry, OpenFGA, Keycloak, OpenBao, Postgres, Redpanda, OpenTelemetry, and the Akwara Cafe systems. We build the MCP gateway, the admin console, the connectors, artifact versions and the style filter, the outbox relay, the OpenFGA tuples derived from an approved map, and the hospitality pack plus client config.

**Options turned down.** Writing the agent loop, the staff chat clients, or a second permissions engine.

**Why.** Those pieces already exist. The map, the gateway that enforces it, and the connectors are what this product adds.

**What it costs us.** We live with the limits of the releases we pin. Rakazo v0.9.0 is one of those limits. See decision 8 and decision 9.

**Where it's argued.** [Brief, How it is built](01-product-brief.md#how-it-is-built). [Architecture, What we build and what we assemble](04-architecture.md#what-we-build-and-what-we-assemble).

## 14. The gateway is the only door

**Decision.** An agent calls only the gateway. It does not open HelixDB, and it does not hold a connector secret (R8). The gateway checks OpenFGA, then reads or calls the connector.

**Options turned down.** Registering Odoo, Frappe, or Nextcloud as MCP servers on the agent. Letting the agent query HelixDB with its own credential.

**Why.** A secret on the agent, or a direct query, skips the approval step and the audit row.

**What it costs us.** Every read and write pays for a gateway hop. That is the point of the hop.

**Where it's argued.** [Architecture, Shape](04-architecture.md#shape). [Ontology, How agents use it](06-ontology.md#how-agents-use-it).

## 15. The audit log wins over the email

**Decision.** Email is a readable copy of an approved action. The audit log is the source of truth. If they disagree, the log wins (R21).

**Options turned down.** Treating the mailbox as the record.

**Why.** Mail can be missing or wrong. The log is append-only and hash-chained.

**What it costs us.** An auditor must be shown the log, not only the Mailpit message.

**Where it's argued.** [Brief, Systems and interfaces](01-product-brief.md#systems-and-interfaces). [Security model, Audit](05-security-model.md#audit).

## 16. The demo secret store is OpenBao

**Decision.** Akwara Cafe's compose runs OpenBao. Secrets are read for one connector call and then dropped (R11).

**Options turned down.** Infisical in the demo. The requirements still allow Infisical for a client that already runs it. The demo does not.

**Why.** One store is enough to show the control. The requirements did not force a single product for every client.

**What it costs us.** A client on Infisical needs an adapter we have not built. The demo does not prove that adapter.

**Where it's argued.** [Security model, Secrets](05-security-model.md#secrets). [Architecture, Deployment](04-architecture.md#deployment).
