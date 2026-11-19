# Build plan

This is the order of work for v0.1 after the foundation. It follows the [brief](01-product-brief.md), the [requirements](02-prd.md), the [simulator](03-demo-company.md), the [architecture](04-architecture.md), and [decision 19](07-decisions.md#19-build-the-map-from-the-systems-and-test-with-the-simulator).

v0.1 proves the product on the simulated cafe, then on a second, different simulated business. Connect a new company's systems. Nobody writes the org chart or the permissions by hand. Ramonda builds a correct map, gives every position the right access, and the agents start useful routine work within days.

Do not open GitHub issues from this plan. There is no ticket breakdown yet.

The wave plan merged in PR 80 is withdrawn. Where an older document still describes that plan, this file and decision 19 win.

<a id="how-an-agent-counts-as-done"></a>

## How a stage counts as done

The test is open-ended. A person in a position asks in their own messy words. A later run uses new wording. The agent also does the duties it has when nobody asked. A grader scores the run against the simulator's hidden record.

A script that calls tools and expects a fixed sentence does not pass a stage. `verify/ramonda check 1` may still pass underneath. A green check leaves the stage unpassed.

Score a run on these points.

1. Facts. The answer matches the hidden record. A wrong branch, a wrong week, or a figure the record does not contain fails.
2. Access. The answer stays inside the position. A leak fails, including in an alert, an email, or a file.
3. Tone. A staff member can use the answer without learning a tool name, a topic name, or a table name.
4. Initiative. From suggest onward, the agent tells the positions the map names. Other positions get no figures. Nobody had to ask. Watch does not send that message.
5. Approval. A write the map marks as gated stays out of the client system until the approving position decides in Ramonda's step. A routine write the map allows may proceed. The audit row names the actor and, on a standing run, the accountable position.

Stage gate for an agent.

- Watch passes when the owner's log is right and no staff were messaged.
- Suggest passes when the positions the map names were told, and any gated write is still pending.
- Act passes when the ungated duties run with nobody asking, and every gated write is still pending for the approving position.

The manual's owner raises the stage after that pass. The agent cannot raise its own stage.

<a id="0-repo-foundations"></a>
<a id="1-amina-reads-westlands-sales"></a>

## Foundation

Slices 0 and 1 are done. They stay the foundation. Later stages build on them and do not replace them.

**Goal.** A guarded repo and a gateway that can read Odoo as the signed-in person, with a secret borrowed for one call and a hash-chained audit row.

**What is built.** The layout in [decision 18](07-decisions.md#18-guard-the-repo-before-feature-work). The Rust gateway, Keycloak, OpenBao, the hash-chained Postgres audit log, TLS, and mutual TLS to the Odoo connector. Rakazo v0.9.0 unmodified. The Odoo connector. The local Compose file. `verify/ramonda check 1`.

The relay, the outbox crate, the console, and the connectors other than Odoo are scaffolds. HelixDB, Foundry, OpenFGA, and Redpanda are absent.

`scripts/seed_akwara_cafe.py` loads the fixed Westlands rows the safety net reads. It is the one Python file outside `connectors/`, which is a repo rule, not a product rule. The simulator replaces it. Do not extend it. `scripts/drive_rakazo_sign_in.sh` drives the old named sign-in. Do not extend it.

The anchor `1-amina-reads-westlands-sales` is the old name of slice 1. That slice is this foundation. The named question is not the product test.

**Done.** Already done. `verify/ramonda check 1` is the safety net. It is not a stage.

## 1. Simulator

**Goal.** The cafe starts to run itself. Begin with one branch and about one month, written into Odoo and the HR system. Grow later. Nobody types the rows.

**What is built.** A simulator that reads the business description and writes the systems. It stores a hidden record of what it meant to happen. The first slice of noise can be small. Hires, a late delivery, and a messy HR title are enough to show the record is doing the work. The full noise list is in [03-demo-company.md](03-demo-company.md).

**Done.** A person asks, in their own words, what happened at that branch that month. The grader can score the answer against the hidden record, using the Odoo and HR rows the simulator wrote. A second run does not need a person to edit those systems. No row was planted as the answer. `verify/ramonda check 1` may still pass and does not pass this stage.

## 2. Map steward

**Goal.** The steward builds the org chart and the live map from the systems stage 1 filled. The check is the simulator's true org chart, which the steward does not read.

**What is built.** The mirror into Postgres. Helix Foundry drafting into the staging HelixDB. The steward. The live HelixDB that only the steward updates. Comparison against the true chart. A flagged difference when HR title drift and the other sources disagree.

**Done.** A person asks who holds a position and who that position reports to, in messy words. The answer matches the hidden org chart. A drifted HR title is mapped to the right position, or it is flagged for a person. The live map was not typed in. A Foundry refresh does not overwrite the live database. Sales for the month are still read from Odoo, not from HelixDB.

## 3. Position access

**Goal.** OpenFGA is filled from the live map. A change of position changes access with no per-person rule.

**What is built.** Tuple generation from positions, responsibilities, and approval roles. The pair switch in [decision 4](07-decisions.md#4-permissions-switch-with-the-map-as-one-pair).

**Done.** Two positions ask for the same kind of fact and each answer stays inside that position, scored against the hidden record of who held which position. Move one simulated person from one position to another. Access follows the move with no new permission row for that person. A failed tuple write leaves the previous pair in force.

## 4. Position agents

**Goal.** One or two agents, each belonging to a position, do real messy work.

**What is built.** A human-owned manual, the stages watch, suggest, and act, a schedule or a Redpanda wake-up, and Ramonda's approval step for a risky write. The outbox and the relay land here if the agent writes a client system. They can land earlier if stage 2 needs Redpanda for map changes. Do not add them before something reads them.

**Done.** Fresh messy questions from the people in those positions, plus a duty that runs with nobody asking. The rubric in [How a stage counts as done](#how-a-stage-counts-as-done) passes against the hidden record. The agent passes watch, then suggest, then act, in that order. A risky write stays pending until the approving position decides in Ramonda's step. A Rakazo card alone leaves the system unchanged. `verify/ramonda check 1` may still pass and does not pass the agent.

## 5. Grow

**Goal.** The cafe becomes the full description. About six months of history, then the simulator keeps running. More branches, the rest of the noise, and more position agents. Then a second simulated business that is not a cafe, through the same path, with nobody hand-writing its map.

**What is built.** The rest of the cafe systems the description names, the remaining agents, and a second simulator description with its own hidden record. The second business is not specified in this repo. Do not invent its industry in code before the owner describes it.

**Done.** The cafe's open questions and unprompted duties match its hidden record across the branches that are running. The second business gets a correct org chart, position access, and useful routine work from its own systems, graded against its own hidden record. A person in the first business cannot read the second business's map or log. No module is named for either company.

<a id="4-the-waste-agent-notices"></a>

## Where the old plan went

PR 80 replaced an earlier slice list with five waves. Decision 19 replaces both. The table says where each idea went.

| Old idea | Where it went |
| --- | --- |
| Slice 0, repo foundations | Kept. [Foundation](#0-repo-foundations) |
| Slice 1, a named person reads Westlands sales | Kept as plumbing. The named question is not the product test. `verify/ramonda check 1` stays as the safety net |
| Slice 2, allowed and refused for named people | [Stage 3](#3-position-access), by position |
| Slice 3, a write waits | [Stage 4](#4-position-agents), for a risky write. The outbox and Redpanda come with the first reader |
| Slice 4, the waste agent notices | Dropped as a scripted scenario. Unprompted duties are stage 4 and stage 5, graded on the hidden record |
| Slice 5, house-style report | Dropped from v0.1 |
| Slice 6, the watcher | The steward applies ordinary map updates. An alerting agent still cannot pause a run. A separate watcher is not a stage |
| Slice 7, a named admin approves every map version | Dropped. [Decision 3](07-decisions.md#3-the-map-goes-live-only-after-a-person-approves-it) is superseded. A person is asked only on disagreement or a sensitive change |
| Slice 8a, full seed and named staff | The seed is replaced by [stage 1](#1-simulator). Do not extend `scripts/seed_akwara_cafe.py` |
| Slice 8b, a named barista's shifts | Dropped as a scripted check. Shifts stay in HR. Access is stage 3 |
| Slice 8c, the approval email | Not a stage. If mail is sent, the audit log still wins |
| Slice 8d, mobile | Not required before stage 5. Rakazo's own client is the app |
| Slice 8e, pack version 2 and a planted note | Dropped. Do not plant an instruction |
| Slice 9, the nine checks and a second cafe from a pack | Replaced by [stage 5](#5-grow). The second business is a different business, not a second cafe from a hand-written pack |
| Wave 1, map, manuals, and a person making every draft current | Split across stages 2, 3, and 4. The person no longer approves every draft |
| Wave 2, named branch and barista agents | Stage 4, one or two positions, then stage 5 |
| Wave 3, ops agent, bakery agent, Redpanda, Odoo write | Redpanda and the write path arrive with the stage that reads them. The named agents do not |
| Wave 4, named finance and HR agents, Daraja, pay writes | HR data starts in stage 1 because the org chart is read from it. Finance and pay agents wait for stage 5. The payment log is simulator input, not a scripted match |
| Wave 5, Monday pack, mobile, second cafe | The Monday pack is dropped. The second company is stage 5 and is not another cafe |

## What this plan leaves out

WhatsApp, a fork of Rakazo, a headless browser, a payment that is actually sent, a business-intelligence dashboard, a per-client screen, a hand-written org chart, and a planted answer. Debezium is not in v0.1. Company reports and decks are not in v0.1.

## Rules that stay

- Rakazo stays the unmodified v0.9.0 image.
- An agent calls only the gateway. OpenBao lends a secret for one call.
- OpenFGA is the permission boundary.
- A risky write waits for the approving position in Ramonda's step.
- The audit log is append-only. The log wins over an email copy.
- Languages stay where [decision 17](07-decisions.md#17-the-gateway-and-the-relay-are-rust-connectors-are-python-the-console-is-typescript) put them.
- Foundry sees real client data only under [decision 12](07-decisions.md#12-foundry-sees-real-client-data-only-with-the-clients-approval). v0.1 uses simulated data only.
- Later connectors use the same TLS pattern as the Odoo connector.
