# Product requirements

These requirements turn the [product brief](01-product-brief.md) into checks an engineer can build. The brief is the definition. This document adds no product scope. Where the brief does not specify a design, see [04-architecture.md](04-architecture.md), [05-security-model.md](05-security-model.md), and [06-ontology.md](06-ontology.md).

The order of work, and the done test for each stage, is [08-build-plan.md](08-build-plan.md). An older requirements list numbered R1 to R38 and used named people and planted rows. [Decision 19](07-decisions.md#19-build-the-map-from-the-systems-and-test-with-the-simulator) replaces that list. A historical decision that cites an old R number is describing the document as it was then.

## Users

- A person who holds a position uses the app to ask a question, to propose an action, and to receive an alert.
- The person who holds the approving position approves or declines in Ramonda's own step. A Rakazo approval card does not count.
- A person who holds the admin position resolves a disagreement in the map, or a sensitive change, and can pause an agent from the console.
- An auditor reads the audit log and cannot change it.

The worked example is the Akwara Cafe simulator in [03-demo-company.md](03-demo-company.md). Positions are in that description. People who fill them come and go. Do not write a requirement that names a person.

## Core flows

### 1. Ask from a position

1. The person signs in as themselves.
2. They ask in their own words.
3. The gateway reads the client's systems as that person. The agent holds no credential.
4. The answer includes only what that person's position allows.
5. The same question from another position comes back different where the positions differ.

### 2. Routine work with nobody asking

1. A schedule, or a change event, wakes the agent for a position.
2. At watch, the agent records the finding and messages nobody.
3. At suggest, it tells the positions the map names, and any gated write stays pending.
4. At act, it does the routine work that position is allowed to do alone.
5. A write that changes a client system still waits for the approving position when the map says so.

### 3. Approve, write back, and record

1. A person, or the agent, proposes a change that the map marks as needing approval.
2. The gateway returns pending and does not call the client system.
3. The person who holds the approving position approves or declines in Ramonda's own step. The gateway records the decision.
4. A decline writes nothing. The decision is still an audit row.
5. An approval writes the change through the gateway into the existing system.
6. The action and its audit event commit together in Postgres. A relay copies the committed event to Redpanda once that path exists.
7. Email may carry a readable copy. If the copy and the log disagree, the log wins.

### 4. Keep the map current

1. A mirror job copies the useful parts of the connected systems into one Postgres database.
2. Helix Foundry drafts a system model from that database and loads it into a staging HelixDB.
3. The map steward writes the checked result into a separate live HelixDB. Foundry's own refresh must not write that live database.
4. OpenFGA is filled from the live map.
5. A person is asked only when the sources disagree, or when the change is sensitive.

## Map

**R1.** The map is the org chart and the links around it. HelixDB holds structure and links only. Sales, shifts, and payments stay in the client systems. Agents read those live through the gateway.

Done when the live map for the simulated month matches the simulator's hidden org chart, and a sale is read from Odoo rather than from HelixDB. Stage 2 in the build plan.

**R2.** Ramonda builds the observed chart from the connected systems. A chart the company supplies is stored separately as the stated chart, with the source and the date on every line. Neither chart replaces the other. Nobody types the map in by hand.

Done when a run produces the live map with no hand-written nodes. A stale supplied chart stays beside the observed chart. A small obvious difference is logged. A difference that would change who can approve or who can see what is one question, and the paper does not win it by default.

**R3.** Helix Foundry drafts into the staging HelixDB it owns. The map steward writes the live HelixDB. A Foundry refresh must not overwrite the live database.

Done when a Foundry refresh changes the staging database and leaves the live database as the steward last wrote it.

## Permissions

**R4.** The same question gets a different answer by position.

Done when two positions ask the same messy question and each answer stays inside that position, scored against the simulator's hidden record.

**R5.** OpenFGA is filled from the live map. Access follows the position. There is no permission rule per person. The model does not grant access.

Done when a person who moves from one position to another gains and loses access with no new rule written for that person.

**R6.** A person signs in as themselves, through Keycloak or the client's OIDC provider.

Done when the session is that person, not a shared login.

## Gateway and connectors

**R7.** A read or a write goes through the gateway. The agent holds no credential. OpenBao lends a secret for one call, and the gateway drops it when the call returns.

Done when an agent process has no system password or token, and a signed-in call runs as that person.

**R8.** When a person asked, the gateway acts as that person. When nobody asked, it acts as the agent for that position. It does not use a shared credential.

Done when an unattended run is audited as that agent, and the audit row also names the position that is accountable.

**R9.** A connector is written once per system and reused. The cafe uses Odoo, Frappe HR, a simulated M-Pesa transaction log, and a mailbox. No money is sent. The log's messages should look realistic. The exact text of a real M-Pesa message is a to-do until the owner supplies an example. Do not invent that format.

Done when two simulated companies on the same system share one connector and differ in the data the simulator wrote.

## Approvals

**R10.** A write the map marks as needing approval waits for the approving position. The training stage does not bypass that wait. A routine write the map allows for that position does not wait.

Done when a gated action is absent from the client system while it is paused, and after a decline. Stage 4 is the test of that pause. An ungated routine write at act is allowed through.

**R11.** The approve or decline that counts is Ramonda's own step, stored by the gateway. A Rakazo approval card does not release the write. A decline writes nothing and is still audited.

Done when a Rakazo card with no Ramonda decision leaves the client system unchanged, and the log contains the gateway decision.

**R12.** A data-changing action runs only when a rule on the map, or a human approval outside the model, allows it. Text the agent read cannot grant that.

Done when an instruction inside a business record does not change an order, a permission, or a secret.

## Audit and events

**R13.** The audit log is append-only and hash-chained. It is the source of truth when an email copy disagrees.

Done when the application cannot update or delete a row, and a conflicting email does not override the log.

**R14.** An action and its event commit together in Postgres and are relayed to Redpanda, so a committed action is not lost and a rolled-back action publishes nothing.

Done when the relay test in the architecture's event section passes. This requirement waits until Redpanda is in the stamp.

**R15.** Events and the audit stream run on Redpanda. Standing agents and the map steward read that stream. A consumer does not classify the event for them.

Done when a change in a client system reaches the steward through Redpanda, and no scenario rule in our code decides that the change matters.

## App and notifications

**R16.** Staff use the Ramonda web app, and the Rakazo mobile client, to chat, to take Ramonda's approval step, and to receive alerts. WhatsApp is not a channel.

Done when a question, Ramonda's approve or decline, and an alert work without WhatsApp. Mobile is not required to pass the earlier stages.

## Admin console

**R17.** The console is where a person resolves a map disagreement or a sensitive change, sees connected systems and the audit log, and pauses an agent. It does not chart sales. There is no per-client console.

Done when that person can pause an agent and can record a decision on a flagged map change, and the map steward cannot pause anyone.

## Reports and decks

**R23.** A position agent produces a report or a deck from data that position may see. The grader scores it against the simulator's hidden record.

Done when one such file is produced in stage 4 or stage 5, its figures match the hidden record, and a position that may not see a source does not receive the file. Do not build the old planted Monday pack, finance deck, or excluded draft.

## Simulator

**R18.** The cafe simulator writes history from the business description into the real systems and keeps a hidden record. It does not plant answers.

Done when stage 1 of the build plan passes, and a later stage can grade an open question against that hidden record.

**R19.** v0.1 then runs a second, different simulated business through the same path. Nobody hand-writes that company's map.

Done when stage 5 of the build plan passes.

## Security

**R20.** One client is one stamp. A person in one stamp cannot read another client's map, records, prompts, or audit log.

**R21.** The product must be assessable for SOC 2 and ISO 27001. That is readiness, not a certification. Detail is in [05-security-model.md](05-security-model.md).

**R22.** Helix Foundry may see a client's real data only with that client's own model key, or with written approval of a provider. v0.1 uses simulated data only.

## Non-functional requirements

Traces use OpenTelemetry once the collector is in the stamp. No response-time target is set. Do not pass or fail a stage on speed.

## Out of scope

- A business-intelligence dashboard, or a replacement for a data warehouse.
- A replacement for the client's systems of record.
- A fork of Rakazo.
- An interface built for one client.
- WhatsApp.
- A hand-maintained org chart, a per-person permission table, or a planted answer.

## Acceptance

Run the stages in [08-build-plan.md](08-build-plan.md). Each stage is done when its open questions, and the duties that run with nobody asking, match the simulator's hidden record.

`verify/ramonda check 1` remains the safety net for the plumbing in slices 0 and 1. A green check does not pass a stage.
