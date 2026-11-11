# Product brief

Agreed definition of Ramonda, from Hassan Kulubya, Akwara-SuperIntelligence, Nairobi.

Ramonda is a governed AI workforce for organisations. Always-on agents work across roles, departments, and access levels, over a live model of the business called the map (the ontology). The map holds the business's things (branches, products, staff, suppliers, orders), the links between them, the actions people can take, and the permissions on who can see and do what.

## Buyers

Large organisations (Fortune 500 scale) and private-equity firms with portfolio companies. The buyer at a PE firm is the operating partner. Work starts with one portfolio company and one named problem, then the map and the rules are reused across similar portfolio companies. The charge is for outcomes, not for hours.

## Problem

Enterprises cannot safely deploy agents across roles. A generic agent does not respect who is allowed to see or do what, and it cannot act in existing systems with a sign-off and an audit trail. Each department ends up with its own disconnected bot.

## What it does

1. The same question gets a different answer by role and permission.
2. An action goes to the right approver before it is written back into the client's existing system, with an immutable audit record.
3. Always-on agents watch events and flag problems before anyone asks.
4. Departments collaborate without seeing each other's restricted data.

## Systems and interfaces

Ramonda adds no new dashboard. Agents read and write the client's existing systems (point of sale, inventory, HR, accounting, M-Pesa, email, and others) via MCP servers, API wrappers exposed as MCP, and change events. Headless browser automation is the last resort. All access goes through Ramonda's MCP gateway, acting as the specific person who asked. Agents never hold credentials.

Staff use a Ramonda web and mobile app to chat, approve or decline, and receive push alerts. The app is Ramonda's own, so the product does not depend on WhatsApp. Email carries a human-readable copy of approved actions and summaries. The audit log is the source of truth. A thin admin console covers roles, connected systems, approval rules, the audit log, and evals. There is no custom dashboard per client.

## How it is built

Assemble mature open source, and build only what is different: the map with its rules, the MCP gateway that enforces them, and the connectors. Rakazo, an open-source always-on agent harness, is consumed unmodified for agents, chat, Spaces, and the app. HelixDB (graph and vector) stores the map; Helix Foundry drafts it. OpenFGA holds permissions. Identity is Keycloak, or the client's Entra or Okta, via OIDC. Secrets sit in OpenBao or Infisical. Events and audit start as a Postgres outbox and move to Kafka-API streaming. Traces use OpenTelemetry. Architecture detail belongs in `04-architecture.md`.

## Security

Enterprises will audit this, so security is a first-class requirement. Agents never hold credentials. Everything an agent reads is untrusted (prompt injection), so a data-changing action requires a rule or a human approval outside the model. Tenants are isolated. The audit log is append-only. A watcher agent over the audit stream is a second layer. The aim is SOC 2 and ISO 27001 readiness.

## Out of scope

Not a BI dashboard or a data-warehouse replacement. Not a replacement for the client's systems of record. Not a fork of Rakazo. Not a custom UI per client. Not dependent on WhatsApp.

## Example

For example, a café chain like Artcaffe in Kenya. This is illustrative. A branch manager asks why croissant waste is up. The agent pulls POS sales and bakery deliveries, suggests cutting weekday orders, and routes that to the regional operations lead for approval. On approval, the change is written into the ordering system with an audit record. A finance analyst asking the same question also sees margins. A barista sees only their shifts.

## How we will know it works

The test is a realistic fake company: a café chain with about five branches, a central bakery, three suppliers, about forty staff in six roles, and four connected systems. Two people ask the same question and get differently permissioned answers, and one action is approved and written back to an existing system with an audit record.
