# Decisions

This log is why a choice was made. A client auditor, or a new engineer, should be able to see the decision, what we refused, and where the argument lives. It records choices already made in the [brief](01-product-brief.md), the [requirements](02-prd.md), the [architecture](04-architecture.md), the [security model](05-security-model.md), the [ontology](06-ontology.md), and the [build plan](08-build-plan.md). It does not add a choice those docs do not already state.

To add a decision, append the next number. To change one, add a new entry and mark the old entry **Superseded by N**. Do not delete or rewrite the old text.

## 1. Consume Rakazo unmodified

**Decision.** Rakazo is the agent runtime, the chat, and the staff web and mobile clients. We pin a release. We do not fork it and we do not patch it (R33).

**Options turned down.** A harness we write. A fork so we can change login or approvals.

**Why.** The loop, the clients, and the harness are mature. Our difference is the map, the gateway, and the connectors. A fork would be ours to rebase.

**What it costs us.** If a release cannot do something we need, we stop and record the gap. We do not patch our way through it.

**Where it's argued.** [Brief, How it is built](01-product-brief.md#how-it-is-built). [Architecture, Agent runtime](04-architecture.md#agent-runtime).

## 2. Redpanda from the start

**Limit.** The text below retries with the same key. It does not say how the connector remembers that key if it crashes after the client system has applied the write and before it stores the result. A second call that arrives while the first call is still in flight is outside this text. That gap is open. Do not treat Odoo as deduplicating the key.

**Decision.** Events and audit run on Redpanda from the start (R15). Postgres commits an action and its event in one transaction. A relay publishes the committed outbox row. The connector call uses an idempotency key. If the gateway dies after the client system has applied a write, it retries that approved action with the same key. It does not retry an action that is still waiting for a person (R16).

**Options turned down.** Postgres only, with a bus added later. Debezium in the Akwara Cafe demo.

**Why.** The audit stream, the watcher, standing agents, schedules, and artifact lineage all need the same facts. Two writes, one to Postgres and one to the bus, can lose one of them. The outbox is the handoff, not a temporary bus. Debezium can replace the relay later. The outbox table is the contract. A Connect cluster is more process than the demo needs.

**What it costs us.** Every stamp runs Redpanda, including one café. We own a small relay.

**Where it's argued.** [Architecture, Events](04-architecture.md#events).

## 3. The map goes live only after a person approves it

**Superseded by [19](#19-build-the-map-from-the-systems-and-test-with-the-simulator).** The map steward writes the live map. A person is asked only when sources disagree, or when the change is sensitive. Foundry still must not write the live HelixDB. The text below is the old decision.

**Decision.** HelixDB stores the approved map (R1, R3). Helix Foundry drafts a version. Versions do not change. Nothing in the live database changes until Nelly Achieng approves it. In Foundry that step is Make current. An automatic Foundry load must not write this stamp's live HelixDB. A refresh that would change who owns something, who cares, a role, who may read a type, or who is accountable stays a proposal.

**Options turned down.** Hand-building every node. Letting Foundry's scheduled refresh write the live graph. Treating a draft as the map staff rely on.

**Why.** A model must not publish the map by itself. Foundry does not write back to client systems, and it does not know our permissions.

**What it costs us.** A new owner or a new supplier is not in the map until a person approves a version. Sales and deliveries are not delayed by that. They are read from the client system when the agent asks.

**Where it's argued.** [Ontology, How the map is built and changed](06-ontology.md#how-the-map-is-built-and-changed). [Architecture, The map](04-architecture.md#the-map).

## 4. Permissions switch with the map, as one pair

**Read with [19](#19-build-the-map-from-the-systems-and-test-with-the-simulator).** The live map and its OpenFGA tuples still change as one pair. The steward writes routine updates. A person is not required for every version. Access the new map would remove expires after 15 minutes if the new tuples have not committed. The text below is the older wording, and it does not name that limit.

**Decision.** OpenFGA tuples are rebuilt only from an approved map (R3, R7). A request uses one pair: a map version and the tuples written from that version. The gateway switches only after the new tuples commit. If that write fails, the previous pair stays current. The new Helix load is not served. There is no extra grace period after the new tuples commit.

**Options turned down.** Letting the model grant access. Serving the new map while the old tuples are still in force. A tenant column instead of a real switch.

**Why.** A retrieval bug in Helix must not widen what OpenFGA refused. A half-updated pair would do that.

**What it costs us.** Access the new map would remove stays in force until the new tuples commit. Nelly is alerted on the first failure. The gateway retries. It does not lock the whole company.

**Where it's argued.** [Ontology, How the map is built and changed](06-ontology.md#how-the-map-is-built-and-changed). [Security model, Identity and access](05-security-model.md#identity-and-access).

## 5. Agents notice. They are not scripted per scenario

**Read with [19](#19-build-the-map-from-the-systems-and-test-with-the-simulator).** Agents still notice from events. They are not scripted per scenario. The names in the text below are the old demo. Responsibility sits on a position.

**Decision.** An always-on agent is woken by `{tenant}.changes` and decides what matters (R20). Who would care is read from the map: `Owns` and `CaresAbout`. Amina owns Westlands. Waste cost matters to her and to Grace. Memory may inform the decision. It does not grant authority. `{tenant}.triggers` is only for schedules and outside webhooks.

**Options turned down.** A hand-written rule per scenario, such as a waste threshold that raises the alert itself.

**Why.** A script per situation does not survive the next company. The map already says who is responsible.

**What it costs us.** The agent can miss something, or raise something a person would have filtered. That is a judgement, not a permission.

**Where it's argued.** [Architecture, Agent runtime](04-architecture.md#agent-runtime). [Ontology, Responsibility and interest](06-ontology.md#responsibility-and-interest).

## 6. One identity per standing agent

**Read with [19](#19-build-the-map-from-the-systems-and-test-with-the-simulator).** One agent is still one principal, with limits. The accountable human is whoever holds the approving position. Do not key the agent to a named person. The text below names people from the old demo.

**Decision.** Each standing agent is one principal, like a new hire, not one identity per scenario (R8). The Akwara ops agent has a role, explicit limits, and a named human manager. When nobody asked, the gateway acts as that agent. It never uses a shared credential. It may read within its role. It may take a small reversible step that does not change a client system, such as drafting a note. It asks a human when it is unsure, when the step is irreversible, or when the step is outside its role. A write to a client system still follows the approval rules (R12, R14). The audit row names the agent and the accountable human. When a person asked, the gateway acts as that person.

**Options turned down.** A shared service login. A fresh identity invented for each event.

**Why.** An auditor has to see who acted. A shared password hides that.

**What it costs us.** Every standing agent needs a principal, limits, and a named manager before it runs.

**Where it's argued.** [Architecture, Agent runtime](04-architecture.md#agent-runtime). [Security model, Identity and access](05-security-model.md#identity-and-access).

## 7. The watcher records and alerts. A human pauses

**Superseded by [19](#19-build-the-map-from-the-systems-and-test-with-the-simulator).** There is no separate watcher. The map steward asks a person when sources disagree, or when a change would alter who can approve or who can see what. The steward cannot pause a run. A person pauses an agent from the console. The text below is the old decision.

**Decision.** The watcher reads `{tenant}.audit` and `{tenant}.changes` (R18). It may record a finding and alert the client admin. For Akwara Cafe that person is Nelly, including when a change suggests the map is behind, such as a new manager, branch, or supplier. It cannot stop a run, pause an agent, edit the map, or write tuples. Pause is a control on the admin console. A human uses it (R32).

**Options turned down.** A watcher that blocks a later action, or that applies a map change itself.

**Why.** A second model must not be able to change the books or the map. A person makes that call.

**What it costs us.** A bad run continues until a person pauses it. A pause does not undo a write the client system already accepted.

**Where it's argued.** [Architecture, Audit](04-architecture.md#audit). [Ontology, How the map is built and changed](06-ontology.md#how-the-map-is-built-and-changed). [PRD, R18](02-prd.md#audit-and-events) and [R32](02-prd.md#admin-console).

## 8. The gateway learns who is calling from its own OAuth token

**Read with [19](#19-build-the-map-from-the-systems-and-test-with-the-simulator).** `verify/ramonda check 1` gets a Keycloak token for the gateway client and calls the gateway as that person. That path does not go through Rakazo. Rakazo's consent flow runs in the same check only when `DEEPSEEK_API_KEY` is set. The sentence below still stands for that consent flow. Do not fork Rakazo.

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

**Superseded by [19](#19-build-the-map-from-the-systems-and-test-with-the-simulator).** Access comes from the position on the live map. OpenFGA is filled from that position. There is no per-person permission table. A stray title in HR is not itself a grant. The text below is the old split.

**Decision.** `HasRole` is the job. `MayRead` is permission to read a type. David's job is finance analyst. His access to margins is `MayRead` on `BranchMargin`. They are not one link.

**Options turned down.** One link that means both "this is their job" and "they may read this type".

**Why.** A job title must not silently grant every field that job might see. Margin and pay are their own object types so OpenFGA can hide them.

**What it costs us.** The pack has two link types where one might have seemed enough. The names are the ones in the ontology. A rename would be a new entry here, not an edit of this one.

**Where it's argued.** [Ontology, The Akwara Cafe map](06-ontology.md#the-akwara-cafe-map).

## 12. Foundry sees real client data only with the client's approval

**Read with [19](#19-build-the-map-from-the-systems-and-test-with-the-simulator).** This rule still holds. Foundry may see a client's real data only with that client's own model key, or with written approval. v0.1 uses simulated data only. v0.1 runs the self-hosted Docker install at [HelixDB/helix-foundry](https://github.com/HelixDB/helix-foundry), Apache-2.0, and it may use a local model. The hosted Anthropic default in the text below is not the v0.1 path.

**Decision.** Helix Foundry, by default, sends synced tables and up to five documents per set to Anthropic models hosted through Helix. A Pro or Max workspace can use its own Anthropic key instead. Foundry may run on a client's real data only with that client's own model key, or a provider the client approved in writing. Until then it drafts from Akwara Cafe's fake data only.

**Options turned down.** Pointing Foundry at a real client's Odoo or HR data while the hosted default model is still in use.

**Why.** That path is not the Ramonda agent's provider, which is still unset. The client's contract has to cover it.

**What it costs us.** A real client's map cannot be drafted in Foundry until the key or the written approval is in place. The demo is not blocked. Its data is fictional.

**Where it's argued.** [Security model, Threats](05-security-model.md#threats) and [Data handling](05-security-model.md#data-handling). [Ontology, Where it lives](06-ontology.md#where-it-lives).

## 13. Assemble what is mature. Build only what is different

**Read with [19](#19-build-the-map-from-the-systems-and-test-with-the-simulator).** The split between what we assemble and what we build still holds. The map is produced by the steward from the company's own systems. A pack, if used, is only a starting set of agents and position templates.

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

## 17. The gateway and the relay are Rust. Connectors are Python. The console is TypeScript.

**Read with [19](#19-build-the-map-from-the-systems-and-test-with-the-simulator).** The language split still holds. The local stamp runs the Rust gateway, and check 1 reaches it with a Keycloak token. Rakazo's MCP consent is the open part of the sentence below. See decision 8. Do not fork Rakazo.

**Decision.** The MCP gateway is Rust from day one, with no Python stopgap. Connectors are Python 3.12, typed, using the official MCP Python SDK. The outbox relay is Rust, in the same Cargo workspace as the gateway. It is part of the same write path, the Postgres outbox to Redpanda. The relay's language is the least load-bearing part of this decision and is open to revision. The admin console is TypeScript, built with Vite, with bun as the package manager. It is not Next.js.

**Options turned down.** A Python gateway, rewritten in Rust later. Next.js for the console. One language for every component we build.

**Why.** The gateway is the hot path every agent action goes through. It is a security boundary. It learns the caller from Keycloak, asks OpenFGA, reads the secret from OpenBao, and writes the outbox. Many MCP connections stay open on Streamable HTTP or SSE. Rust keeps tail latency predictable and memory low per connection. Memory safety and a strict type system suit a boundary component. There is no garbage collector. It ships as one small static binary for the per-client Docker Compose stamp. It is the component we would least want to rewrite under load. Connectors are numerous and change often. Odoo, Frappe HR, and similar systems are Python ecosystems, and a connector's speed is bounded by the upstream system. The console is thin. Next.js is too heavy for it. Ramonda is built by AI coding agents, not a human team. Rust's learning curve is not a constraint. The compiler is a safety net for agent-written code. Three languages, each with a narrow, clear job. This supersedes the pre-reset `LANGUAGE.md` ("Python decides, Rust delivers"), now only in the tag `archive/agent-service`. The principle is the same, applied to this design, where Rakazo replaces the old self-built Python agent service.

**What it costs us.** Rust's MCP libraries are less mature than Python's or TypeScript's. Keycloak as the gateway's MCP OAuth server, with Rakazo v0.9.0, is specified and not demonstrated. See decision 8. The first gateway slice has to prove a Rust gateway speaking MCP to Rakazo with Keycloak OAuth before anything is built on it.

**Where it's argued.** [Architecture, MCP gateway](04-architecture.md#mcp-gateway), [Connectors](04-architecture.md#connectors), [Events](04-architecture.md#events), and [App and admin console](04-architecture.md#app-and-admin-console). The first slice that has to show it is [build plan, slice 1](08-build-plan.md#1-amina-reads-westlands-sales).

## 18. Guard the repo before feature work

**Read with [19](#19-build-the-map-from-the-systems-and-test-with-the-simulator).** The repo guards still hold. The nine scripted checks are not the product test. `verify/ramonda check 1` is a safety net for the plumbing. The sentence below that says the CLI has no commands describes slice 0. The command exists now. That is not a reason to add more checks.

**Decision.** Feature work starts from a guarded repo ([slice 0](08-build-plan.md#0-repo-foundations)). The layout is the one in [architecture, Reuse](04-architecture.md#reuse) and [decision 17](#17-the-gateway-and-the-relay-are-rust-connectors-are-python-the-console-is-typescript): `core/` holds the Cargo workspace (`gateway/`, `relay/`, the shared `outbox/` contract) and the TypeScript console; `connectors/` holds one Python 3.12 package per system; `packs/hospitality/` and `clients/akwara-cafe/` are config. Boundaries, the comment rule, and the hot-path rule are CI failures, and the error names the allowed alternative. Warnings are errors, on rustfmt, clippy with pedantic, ruff, pyright strict, pytest, `tsc` strict, and Biome. `AGENTS.md` is thin and pairs each rule with the check that enforces it. `verify/` holds a stub of the nine Akwara Cafe checks and a `ramonda` CLI with no commands. pstack is enabled in `.cursor/settings.json` by its marketplace name, which installs Cursor's reviewed release. Ponytail is pinned there by git URL and commit, and that commit's always-on rule is copied to `.cursor/rules/ponytail.mdc` because cloud agents do not run its session hook. TLA+ is written in the slice that writes the code it covers. Slice 0 creates `specs/` and writes no model.

**Options turned down.** A prose style guide, or a human review step, as the way to keep agents honest. ESLint beside Biome, and any linter beyond the set above. Ponytail's `shortcut:` comments. Ponytail's Cursor hook install, which does not run for a cloud agent. Writing the TLA+ models in the scaffold slice. Tracking Ponytail on a floating branch. A git pin of `https://github.com/cursor/plugins` for pstack, which is the marketplace repo and not the plugin. A relay that depends on the gateway. A connector that imports another connector or `core`.

**Why.** Ramonda is built by AI coding agents. There is no human team. [Ponytail](https://github.com/DietrichGebert/ponytail/blob/main/skills/ponytail/SKILL.md) says to write the least new code and take the first rung of its ladder that fully works. Lauren Tan's poteto pyramid, in the talk "All Code Is Slop (Except Mine)" and in [pstack](https://github.com/cursor/plugins/tree/main/pstack), ranks leverage from codebase structure, to static analysis, to verification, to prose, to human review. Agents copy what is already in the tree. A narrating comment, or a line in `AGENTS.md`, does not stop the next agent. A folder boundary and a failing check do. Where Ponytail asks for a `shortcut:` comment, the pyramid wins: the constraint becomes a type, a lint, or a test.

**What it costs us.** CI runs three toolchains before any feature. A pedantic warning is fixed in the code. A hot-path file cannot block, allocate, or sleep, so the caller owns the buffer. The `ramonda` CLI does nothing until the stamp boots and `/create-verification-skill` fills `verify/` in. Slice 3 has to write the outbox recovery model and the approval and permission state machine with the code, because slice 0 left `specs/` empty.

**Where it's argued.** [Build plan, slice 0](08-build-plan.md#0-repo-foundations). The directory names come from [architecture, Reuse](04-architecture.md#reuse). The languages come from [decision 17](#17-the-gateway-and-the-relay-are-rust-connectors-are-python-the-console-is-typescript).

## 19. Build the map from the systems and test with the simulator

**Decision.** Ramonda builds the company map from the systems the company connects. The org chart is positions, reporting lines, teams, and responsibilities. People fill positions. Nothing is keyed to a named person. Access in OpenFGA comes from the position on the live map. Agents belong to positions. They start at watch, then suggest, then act. A risky action waits for whoever holds the approving position. Each agent has a manual a person owns.

A company may also hand over the chart it already has. The steward normalises a spreadsheet, a CSV, a PDF or a slide, a photo of a whiteboard, or the manager fields in HR into that same shape. It stores the result as the stated chart, beside the observed chart it built from the systems. Neither chart replaces the other. Each line keeps its source and its date. Agreements are confirmed. A small obvious difference is applied and logged. A difference that would change who can approve, or who can see what, is one short question to the approving position. When they disagree, the systems outweigh the paper. A new upload is a new version. The comparison runs again, and the old version stays in the map history.

The test is a simulator with a hidden record of what really happened. The first business is Akwara Cafe. A second, different simulated business follows. Scripted checks are a safety net only. `verify/ramonda check 1` is that net for the plumbing that exists today.

Helix Foundry drafts into a staging HelixDB that it may overwrite. The map steward writes a separate live HelixDB. Foundry must not write the live database. v0.1 runs Foundry from [HelixDB/helix-foundry](https://github.com/HelixDB/helix-foundry), self-hosted with Docker, under Apache-2.0. It may use any model, including a local one. [Decision 12](#12-foundry-sees-real-client-data-only-with-the-clients-approval) still holds. v0.1 uses simulated data only.

The owner has since settled the open points below. An industry pack is only a starting set of agents and position templates. The map is always built from the company's own systems. Reports and decks are in v0.1. A position agent produces them, and the grader scores them against the simulator. The cafe chart has a general manager at the top. A position manual lives in that client's directory under `clients/`, and only a person edits it. There is no separate watcher. The map and its OpenFGA tuples still change as one pair. Access the new map would remove expires after 15 minutes if the new tuples have not committed. The second simulated business is a logistics company. HR is Frappe HR. The payment log is a simulated M-Pesa transaction log, and no money is sent. The exact text of a real M-Pesa message waits for an example from the owner. Do not invent that format.

**Options turned down.** A hand-written demo company with named people and planted facts. Per-person permission tables. A person approving every map version. Scripted checks as the main test. The wave plan merged in PR 80. Extending `scripts/seed_akwara_cafe.py` instead of replacing it with the simulator.

**Why.** The scripted checks and the planted seed passed while proving little about a new company. A change of position has to change access without a new rule for that person. A map that a person maintains by hand does not stay current. The simulator writes messy history into the real systems, and the grader can score open questions against a record the agents do not see.

**What it costs us.** The seed script, the named users in the local Keycloak realm, and `verify/ramonda check 1` remain until the simulator replaces them. Do not extend them. Rakazo's consent flow is still open. The idempotency gap after a client-system write is still open. The logistics company's operations are not described yet.

**Where it's argued.** [Brief](01-product-brief.md). [Requirements](02-prd.md). [Simulator](03-demo-company.md). [Architecture](04-architecture.md). [Ontology](06-ontology.md). [Build plan](08-build-plan.md).
