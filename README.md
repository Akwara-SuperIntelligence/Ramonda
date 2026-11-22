# Ramonda

Ramonda gives a company a team of AI agents in that company's real positions, working on its real systems, safely.

You connect the systems. Ramonda works out how the company is organised. Akwara designs and builds an agent for each position the customer wants covered. Those agents do routine work from schedules and events. A person steps in when the action is risky or unusual.

The org chart organises the product. It holds positions, reporting lines, teams, and responsibilities. People fill positions. A record is not keyed to a named person.

Ramonda builds this map from the connected systems and keeps it current. A company may also hand over the org chart it already has. Ramonda keeps that stated chart beside the chart it observed, and it does not let either one replace the other. A person is asked only when a difference would change who can approve or who can see what. Nobody maintains the map by hand.

Access follows the position. OpenFGA is filled from the map, so a change of position changes access. There is no permission rule per person.

An agent belongs to a position. It starts at watch, then moves to suggest, then acts on routine work. A risky action waits for whoever holds the approving position. Each agent has a manual that a person owns. The agent reads that manual and does not edit it.

## What ready means

Ready is a concrete test. Connect Ramonda to a new company's systems. Nobody writes the org chart or the permissions by hand. Ramonda builds a correct org chart and map. It gives every position the right access. The agents start useful routine work within days.

v0.1 has to prove that on a simulated cafe, then on a simulated logistics company. The cafe is described in [Akwara Cafe, the simulator](https://linear.app/akwara-hq/document/ramonda-v01-akwara-cafe-the-simulator-ca85c105a7af). The order of work is in the [Build plan](https://linear.app/akwara-hq/document/ramonda-v01-build-plan-bcc05dff0daa). The reason for this shape is [decision 19, Build the map from the systems and test with the simulator](https://linear.app/akwara-hq/document/ramonda-v01-decisions-log-817852748b33).

## What runs today

Slices 0 and 1 are the plumbing that exists.

- The Rust gateway is the only door from an agent to a business system.
- Keycloak signs a person in.
- OpenBao lends a credential for one call, and the gateway drops it when the call returns.
- Postgres stores a hash-chained audit log.
- TLS covers the local stamp. The Odoo connector requires the gateway's client certificate.
- Rakazo v0.9.0 is the agent runtime. It is not forked. The local stamp uses DeepSeek when `DEEPSEEK_API_KEY` is set.
- The Odoo connector is the business-system connector that runs. Odoo holds the sales and stock used by the safety net.

## What is not built

The simulator, the mirror, Helix Foundry, the staging HelixDB, the map steward, the live HelixDB, OpenFGA, position agents, approvals, the outbox, Redpanda, and the console are not built.

Frappe HR, the payment log, and the mailbox are not in the local Compose file. Connector packages for Frappe HR, Daraja, Mailpit, and Nextcloud are scaffolds. The relay, the outbox crate, and the console package are scaffolds.

`scripts/seed_akwara_cafe.py` loads a fixed Westlands history so the safety net can run. The simulator replaces that script. Do not extend it. `scripts/drive_rakazo_sign_in.sh` drives the old named sign-in. Do not extend it either.

`packs/hospitality/` and `clients/akwara-cafe/` are layout from slice 0. They are not the org chart. Do not fill them with a hand-written company or with planted facts. `clients/akwara-cafe/gateway-mcp.json` only points Rakazo at the gateway.

## Run the local stamp

Run these commands from the repository root.

1. Run `deploy/certs/generate.sh`. It writes a dev CA and the service certificates under `deploy/certs/out/`. Those private keys are not committed.
2. Run `docker compose -f deploy/compose.yaml --profile gateway up`. The gateway and the Odoo connector belong to the `gateway` profile. Without that profile they do not start.
3. Follow [deploy/certs/README.md](deploy/certs/README.md) for the hosts entry and for trusting the dev CA. On any stamp other than this laptop file, leave `RAMONDA_STAMP` unset. The gateway refuses to start when that stamp would use the dev CA, or plain HTTP, for the connector or for OpenBao.

When Odoo is healthy, `python3 scripts/seed_akwara_cafe.py` reloads the old Westlands rows. `verify/ramonda check 1` then runs the safety net. Both commands need the stamp from step 2. A green check does not pass a product stage. The check is described in [verify/feature-map.md](verify/feature-map.md).

## Plans, specs and tickets live in Linear

Plans, specs, decisions, and tickets live in the [Akwara workspace](https://linear.app/akwara-hq). Tickets are in the Ramonda team (key RAM). GitHub issues are not used for planning.

Projects:

- [0. Ramonda overview and reference](https://linear.app/akwara-hq/project/0-ramonda-overview-and-reference-9e8dc09c81d1)
- [1. Simulator](https://linear.app/akwara-hq/project/1-simulator-4de458bbcbba)
- [2. Map steward](https://linear.app/akwara-hq/project/2-map-steward-7dab95bb8206)
- [3. Position-based access](https://linear.app/akwara-hq/project/3-position-based-access-262937e1451d)
- [4. First position agents](https://linear.app/akwara-hq/project/4-first-position-agents-6c5f181ffb94)
- [5. Second business (logistics)](https://linear.app/akwara-hq/project/5-second-business-logistics-9780e3dd0bcc)

Docs:

- [Product brief](https://linear.app/akwara-hq/document/ramonda-v01-product-brief-e338d72b5aca)
- [PRD](https://linear.app/akwara-hq/document/ramonda-v01-product-requirements-prd-8891c38f5804)
- [Akwara Cafe, the simulator](https://linear.app/akwara-hq/document/ramonda-v01-akwara-cafe-the-simulator-ca85c105a7af)
- [Architecture](https://linear.app/akwara-hq/document/ramonda-v01-architecture-fce12b302e80)
- [Security model](https://linear.app/akwara-hq/document/ramonda-v01-security-model-775c99b29a99)
- [Ontology](https://linear.app/akwara-hq/document/ramonda-v01-ontology-what-the-map-holds-6fbd8352129e)
- [Decisions log](https://linear.app/akwara-hq/document/ramonda-v01-decisions-log-817852748b33)
- [Build plan](https://linear.app/akwara-hq/document/ramonda-v01-build-plan-bcc05dff0daa)
