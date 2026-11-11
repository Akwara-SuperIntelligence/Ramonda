# Product requirements

These requirements turn the [product brief](01-product-brief.md) into checks an engineer can build and a tester can run. The brief is the definition. This document adds no product scope. Who buys Ramonda, and that the charge is for outcomes, stays in the brief and is not build work. Where the brief does not specify a design, see `04-architecture.md`, `05-security-model.md`, and `06-ontology.md`.

## Users and roles

Five kinds of people use the product.

- **Staff** use the web and mobile app to ask questions, propose actions, and receive push alerts.
- **Approvers** are staff named by an approval rule. They approve or decline in the app before a change is written back, and before an artifact is marked official or sent outside.
- **Client admins** use the thin admin console for roles, connected systems, approval rules, the audit log, and evals.
- **Akwara operators** onboard a client. They apply an industry pack and that client's config in the same console, inside that client's tenant.
- **Auditors and security reviewers** read the audit log to check a sign-off. They do not change the log.

The worked example is the fake café chain in the brief. It is illustrative. The six roles are below. Permissions the brief does not fix are config. The company shape is under Acceptance.

1. **Branch manager.** Asks about waste, sales, and deliveries at their branch. Proposes a change such as cutting weekday orders.
2. **Barista.** Sees only their own shifts.
3. **Regional ops lead.** Approves or declines an operational change. In the example, the weekday order cut.
4. **Finance analyst.** Asks the same question as the branch manager and also sees margins.
5. **Bakery and supply.** Works the central bakery, the suppliers, and deliveries.
6. **HR.** Works staff records and shifts.

## Core flows

### 1. Ask and get a permissioned answer

1. The staff member signs in as themselves.
2. They ask a question in the app.
3. The gateway reads the client's systems as that person. The agent holds no credential.
4. The answer includes only what that person's permissions allow.
5. The same question from another role comes back different where the permissions differ.

### 2. Propose, approve, write back, and record

1. A staff member proposes a change, or the agent proposes one from their question. The gateway acts as the person who asked. In the example, cut weekday croissant orders.
2. The proposal goes to the approver named by the rule. In the example, the regional ops lead.
3. The approver approves or declines in the app.
4. A decline writes nothing. The decision is still audited.
5. An approval writes the change through the gateway into the existing system, as the person who asked. In the example, the ordering system.
6. The action and its audit event commit together in Postgres and are relayed to Redpanda.
7. The log keeps an immutable record: the action, who asked, the approver's decision, and the system written.
8. Email sends a readable copy of the approved action. The log remains the source of truth.

### 3. An always-on agent alerts the right person

1. A connected system emits a change event. In the example, sales or a bakery delivery showing croissant waste rising. The gateway receives it. The agent holds no credential.
2. An always-on agent checks the event against the map and the rules.
3. If there is a problem, the app push-alerts only people allowed to see it. The branch manager is alerted. The barista is not sent the waste figures.
4. This flow does not itself change data. A write still needs a rule, or a human approval as in flow 2.
5. The brief does not say which identity the gateway uses when nobody has asked. See Open questions. Do not pick one in the build.

### 4. Work across departments without leaking restricted data

1. Two roles work on the same situation, each under their own sign-in. In the example, waste.
2. The finance analyst's view includes margins. The barista's view is only their shifts.
3. A field restricted to one role is not copied into another role's answer, alert, email, or artifact.

### 5. Produce an artifact

1. An agent drafts company work from the client's own data. In the example, the regional ops lead's Monday branch pack, built from point-of-sale sales and bakery deliveries.
2. The draft is shared only with people allowed to see every source it used.
3. It is not marked official, and not sent outside the company, until the approver named by the rule approves it.
4. The approved version is saved through a connector to where staff already work: the client's Drive, SharePoint, or email. It is not put in a new Ramonda dashboard.
5. The audit log records the version, the owner, and the source data. Regenerating the pack writes a new version and leaves the earlier version in place.

### 6. Onboard a client from a pack and config

1. The operator starts the client from an industry pack. For this café, the pack is hospitality.
2. The pack provides a ready-made map (branches, menus, suppliers, shifts), standard roles, standard approval rules, and ready-made agents and evals.
3. The operator applies client config: names, the real org chart, which systems, extra rules, and the client's data.
4. Systems are attached with a connector that already exists. No code is added for this client.
5. Staff sign in as themselves. A second café chain starts from the same pack and different config, on the same core version.

### 7. An auditor reviews the log

1. The reviewer opens the audit log in the admin console and finds the approved write from flow 2.
2. The record shows the action, who asked, the approver's decision, and the system written. They cannot edit or delete it.
3. If an email copy disagrees with the log, the log is the record.
4. A watcher agent has received that audit event from Redpanda. What the watcher may do about a finding is an open question.

## Requirements

### Map

**R1.** The map is a live model of the business: its things, the links between them, the actions people can take, and who can see and do what.

Done when: the demo map includes branches, products, staff, suppliers, and orders, linked from a branch to its staff and its orders.

**R2.** A client map starts from an industry pack and is then changed with client config. Pack versus client map is in `06-ontology.md`.

Done when: the demo café is the hospitality pack plus config, and a name or org-chart entry changes without a code change.

**R3.** HelixDB stores the map. Helix Foundry can draft it, and the draft is then config. Layout is in `04-architecture.md`.

Done when: the demo map is in HelixDB, a Foundry draft can be produced, and that draft can be changed as config.

### Permissions

**R4.** The same question gets a different answer by role and permission.

Done when: the branch manager, the finance analyst, and the barista each ask why croissant waste is up; the analyst also sees margins, and the barista sees only their shifts.

**R5.** People can work on one situation without seeing another role's restricted data.

Done when: a field restricted to one role is absent from another role's answer, push alert, email, and artifact about that situation.

**R6.** A person signs in as themselves: Keycloak, or the client's Entra or Okta, via OIDC.

Done when: a demo user signs in with that provider and the session is that named person, not a shared login.

**R7.** OpenFGA decides whether a read or an action is allowed. The model does not. How the check is called is in `04-architecture.md`.

Done when: OpenFGA allows or refuses both the barista's question and the order-cut write.

### Gateway and connectors

**R8.** A read or write a person asked for goes through the MCP gateway as that person. The agent never holds the credential. When nobody has asked, see Open questions, and still do not give the agent a credential.

Done when: calls for a signed-in person run as that person, and the agent process has no system password or token.

**R9.** Connect a system with an MCP server, an API wrapper exposed as MCP, or change events. Headless browser automation is only for a system with none of those, and it still goes through the gateway and R14.

Done when: each of the four demo connections uses one of the three methods, or browser automation is recorded against a system with no API and no event feed.

**R10.** A connector is written once per system and reused by every client on that system. Odoo, Sage, and M-Pesa are examples.

Done when: two clients on the same system share one connector codebase and differ only in config.

**R11.** Connector secrets sit in OpenBao or Infisical.

Done when: demo credentials are in that store and are not in the agent, the source tree, or the prompt.

### Approvals

**R12.** A data-changing action goes to the approver named by the rule before it is written to the client's system.

Done when: the weekday order cut is not in the ordering system until the regional ops lead approves it.

**R13.** The approver approves or declines in the app. A decline writes nothing. The decision is in the audit log.

Done when: a decline leaves the ordering system unchanged and the log contains that decline.

**R14.** A data-changing action runs only when a rule or a human approval outside the model allows it. Data the agent read cannot grant that.

Done when: with no such rule and no approval, the order cut is not written, even if the agent was told to write it.

### Audit and events

**R15.** Events and audit run on Redpanda from the start.

Done when: the demo produces those records on Redpanda.

**R16.** An action and its event commit together in Postgres and are relayed to Redpanda, so nothing is lost between the two.

Done when: the event still reaches Redpanda if the relay stops after the commit, and a rolled-back action produces no event.

**R17.** The audit log is append-only and is the source of truth.

Done when: the app, the agent, and the console cannot update or delete a record, and a conflicting email does not override the log.

**R18.** A watcher agent reads the audit stream as a second layer, separate from the agent that did the work.

Done when: the watcher receives the approved order-change event from Redpanda.

### App and notifications

**R19.** Staff use the Ramonda web app and mobile app to chat, approve or decline, and receive push alerts. WhatsApp is not a channel.

Done when: the question, the approval, and a push alert work on web and on mobile, with no WhatsApp step.

**R20.** An always-on agent flags a problem from an event before anyone asks, and alerts only people allowed to see it.

Done when: flow 3's waste event alerts the branch manager and does not send the waste figures to the barista.

### Email

**R21.** Email carries a readable copy of an approved action and a summary. The audit log is the source of truth.

Done when: the approved order change produces an email a person can read, a summary of it can be produced from the log, and the log wins if the email is missing or wrong.

### Artifacts

**R22.** An artifact is company work built from the client's own data, such as a report, deck, spreadsheet, SOP, policy draft, forecast, or small internal tool. It is an object in the map, with an owner, its sources, and a version.

Done when: the Monday branch pack is on the map with an owner, its point-of-sale and bakery sources, and a version.

**R23.** An artifact is visible only to people who may see every source it used. Its audience is never wider than the most restricted of those sources.

Done when: the barista cannot open the Monday branch pack, because they cannot see its sales and delivery sources.

**R24.** An artifact is approved before it is sent outside the company or marked official.

Done when: the Monday branch pack is not marked official, and is not sent outside, until the named approver approves it.

**R25.** An approved artifact is saved through a connector to the client's existing storage, such as Drive, SharePoint, or email. It is not kept in a new Ramonda dashboard.

Done when: the approved Monday pack is a file in that storage, written by a connector, and the café has no artifact screen of its own.

**R26.** Every create or edit of an artifact is audited, with lineage to the source data.

Done when: the log for the Monday pack records the owner, the version, and the point-of-sale and bakery sources.

**R27.** Regenerating an artifact creates a new version. It does not overwrite the previous one.

Done when: a second run of the Monday pack leaves the first version intact and records a second version.

### Admin console

**R28.** The console covers roles, connected systems, approval rules, the audit log, and evals. There is no new staff dashboard and no per-client console.

Done when: an admin manages those five items for the demo café in the shared console, and the café has no screen of its own.

### Reuse

**R29.** Core is one codebase and one version for every client: Rakazo, the gateway, permission checks, approvals, audit, the app, and the admin console. Rakazo is unmodified. The core is not forked per client.

Done when: the café and a second client run one core build, with no fork or patch of Rakazo.

**R30.** Per client, only config changes: names, the real org chart, which systems, extra rules, and their data.

Done when: the demo café is a hospitality pack plus config, and removing that config leaves no café-only code.

**R31.** A client request goes into core, a connector, or a pack, so the next client benefits, or it stays config. One-off client code is avoided.

Done when: a request useful to only one café is met in core, a shared connector, a pack, or config, and no module is added for that client alone.

### Security

**R32.** Tenants are isolated.

Done when: a demo-café user cannot read another client's map, records, prompts, or audit log.

**R33.** Everything an agent reads is untrusted, including prompt injection in business data.

Done when: an instruction planted in a sales or delivery record does not change an order, a permission, or a secret, unless a rule or a human approval under R14 allows it and that allowance was not part of the planted instruction.

**R34.** The product must be assessable for SOC 2 and ISO 27001. That is readiness, not a certification claim. Detail is in `05-security-model.md`.

Done when: a reviewer can find demo evidence for R6, R8, R11, R14, R17, R18, R32, and R33.

## Non-functional requirements

### Security

R6, R8, R11, R14, R17, R18, R32, R33, and R34 are the bar. Agents never hold credentials. A data-changing action needs a rule or a human approval outside the model. Tenants are isolated. The audit log is append-only. A watcher reads that stream. The aim is SOC 2 and ISO 27001 readiness.

### Reliability

R16 is the check. No committed action loses its event between Postgres and Redpanda, and no event is published for an action that did not commit.

### Observability

Traces use OpenTelemetry. Layout is in `04-architecture.md`.

Done when: the permissioned question and the approved write each have a trace showing the gateway call and the person it acted as.

### Performance

No response-time or throughput target is set. Do not pass or fail the build on speed.

## Out of scope

Carried from the brief.

- Not a business-intelligence dashboard, and not a replacement for a data warehouse.
- Not a replacement for the client's systems of record.
- Not a fork of Rakazo.
- Not a custom user interface per client.
- Not dependent on WhatsApp.

## Acceptance

Run this on the fake café chain. It is the brief's test of whether the product works. Every other requirement keeps its own Done when.

The company has about five branches, a central bakery, three suppliers, about forty staff, and the six roles above. Four systems are connected. Name them in `03-demo-company.md`. This scenario reads point-of-sale sales and bakery deliveries, writes the ordering system, and produces the Monday branch pack.

1. The branch manager asks why croissant waste is up. The answer uses point-of-sale sales and bakery deliveries.
2. The finance analyst asks the same question and also sees margins.
3. The barista asks the same question and sees only their shifts. The three answers are not the same. Two differing answers would meet the brief; this demo checks all three.
4. A weekday croissant order cut is proposed to the regional ops lead. Until they approve, the ordering system is unchanged.
5. They approve in the Ramonda app. The gateway writes the change into the ordering system as the person who asked.
6. The audit log holds an immutable record: the action, who asked, the decision, and the system written. The action and its event were committed together in Postgres and are on Redpanda.
7. An email copy of the approved action was sent. If it disagrees with the log, the log is the record.
8. Staff used the Ramonda app, not a new dashboard and not WhatsApp.
9. The agent drafts the regional ops lead's Monday branch pack from point-of-sale and bakery data. Someone who cannot see those sources cannot open it. It is not marked official until it is approved. The approved pack is saved to the client's existing storage, and the audit log records the version and the sources. Running it again keeps the first version and writes a second.

## Open questions

Unresolved in the brief. Do not close them in code.

1. **Identity when nobody has asked.** The gateway acts as the person who asked. That does not cover an always-on read, or a write allowed only by a rule, when no person has asked. The brief names no identity and no permission scope for that case. Record the decision in `07-decisions.md`. The security effect belongs in `05-security-model.md`.
2. **What the watcher may do.** It reads the audit stream as a second layer. The brief does not say it may only record a finding, alert a person, or stop a later action. Record the decision in those same documents.
