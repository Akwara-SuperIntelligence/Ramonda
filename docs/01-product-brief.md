# Product brief

Agreed definition of Ramonda, from Hassan Kulubya, Akwara-SuperIntelligence, Nairobi.

Ramonda is a governed AI workforce for organisations. Always-on agents work across roles, departments, and access levels over the map, a live model of the business (the ontology): its things (branches, products, staff, suppliers, orders), the links between them, the actions people can take, and who can see and do what.

## Buyers

Large organisations (Fortune 500 scale) and private-equity firms with portfolio companies. The buyer at a PE firm is the operating partner. Start with one portfolio company and one named problem, then reuse on similar companies. Charge for outcomes, not for hours.

## Problem

Enterprises cannot safely deploy agents across roles. A generic agent does not respect who is allowed to see or do what, and it cannot act in existing systems with a sign-off and an audit trail. Each department ends up with its own disconnected bot.

## What it does

1. The same question gets a different answer by role and permission.
2. An action goes to the right approver before it is written back into the client's existing system, with an immutable audit record.
3. Always-on agents watch events and flag problems before anyone asks.
4. Departments collaborate without seeing each other's restricted data.
5. Agents produce company work from the client's own data, in the client's own branding, templates and formats, learned from the artifacts the company has made before: reports, decks, spreadsheets, SOPs, policy drafts, forecasts, and small internal tools.

## Systems and interfaces

No new dashboard, and no custom dashboard per client. Agents read and write the client's existing systems (point of sale, inventory, HR, accounting, M-Pesa, email, and others) via MCP servers, API wrappers exposed as MCP, and change events. Headless browser automation is the last resort. All access goes through Ramonda's MCP gateway. When a person asked, it acts as that person. When nobody asked, it acts as the standing agent's own identity, never a shared credential. Agents never hold credentials. Artifacts are saved where staff already work (the client's Drive, SharePoint or email), never in a new Ramonda dashboard.

Staff use a Ramonda web and mobile app to chat, approve or decline, and receive push alerts. The approval that counts is Ramonda's own step, recorded by the gateway. A Rakazo approval card alone does not release a write. The app is Ramonda's own, so it does not depend on WhatsApp. Email carries a readable copy of approved actions and summaries; the audit log is the source of truth. A thin admin console covers roles, connected systems, approval rules, the audit log, and evals, and a human can pause a standing agent from it.

## How it is built

Build only what is different (the map and its rules, the MCP gateway that enforces them, and the connectors) and assemble the rest from mature open source. Rakazo, an open-source always-on agent harness, is consumed unmodified for agents, chat, Spaces, and the app. HelixDB (graph and vector) stores the map; Helix Foundry drafts it. OpenFGA holds permissions. Identity is Keycloak, or the client's Entra or Okta, via OIDC. Secrets sit in OpenBao or Infisical. Events and audit run on Redpanda from the start; actions and their events are committed together in Postgres and relayed to Redpanda so nothing is lost between the two. Traces use OpenTelemetry. Layout is in `04-architecture.md`.

## How it is reused

Every client gets the same product. What changes per client is configuration, not code.

1. Core, shared by every client regardless of industry: Rakazo, the gateway, permission checks, approvals, audit, the app and the admin console. One codebase, one version, never forked per client.
2. Connectors, shared by every client on the same system: write the Odoo, Sage or M-Pesa connector once and the next client on that system gets it. This library is the moat.
3. Industry packs, shared by every client in the same industry: a hospitality pack, for example, with a ready-made map (branches, menus, suppliers, shifts), standard roles, standard approval rules, ready-made agents and evals. The second café chain starts from the pack. This is what makes the private-equity model work, since funds hold several companies in the same industry.
4. Client config, unique per client: names, the real org chart, which systems, extra rules, their data. Data and settings, never custom code.

A client request goes into core, a connector, or a pack, so the next client benefits, or it stays config. Custom code for one client is avoided. Storage of packs and config is detailed in `04-architecture.md`; pack versus client map is in `06-ontology.md`.

## Security

Enterprises will audit this, so security is a first-class requirement. Agents never hold credentials. Everything an agent reads is untrusted (prompt injection), so a data-changing action requires a rule or a human approval outside the model. Tenants are isolated. The audit log is append-only. A watcher agent reads that stream, may alert an admin, and cannot stop a run. The aim is SOC 2 and ISO 27001 readiness.

## Out of scope

Not a BI dashboard or a data-warehouse replacement. Not a replacement for the client's systems of record. Not a fork of Rakazo. No one-off interface for a single client; new interfaces are built once and reused across clients. Not dependent on WhatsApp.

## Example

The worked example is Akwara Cafe, a fictional Nairobi café chain, the kind of company Artcaffe is. Artcaffe is not a customer. A branch manager asks why croissant waste is up. The agent reads POS sales and bakery deliveries, suggests cutting weekday orders, and routes that to the regional operations lead. On approval, the change is written into the ordering system with an audit record. A finance analyst who asks the same question also sees margins. A barista sees only their shifts.

## How we will know it works

Against Akwara Cafe (about five branches, a central bakery, three suppliers, about forty staff in six roles, four connected systems), two people ask the same question and get differently permissioned answers, and one action is approved and written back to an existing system with an audit record. The company is set out in [03-demo-company.md](03-demo-company.md).
