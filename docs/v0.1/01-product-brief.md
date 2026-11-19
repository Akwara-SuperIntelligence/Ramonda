# Product brief

Ramonda gives a company a team of AI agents in that company's real positions, on its real systems, safely.

You connect the systems. Ramonda works out how the company is organised. Akwara designs and builds an agent for each position the customer wants covered. The agents do routine work from schedules and events. A person steps in when the action is risky or unusual.

Agreed with Hassan Kulubya, Akwara-SuperIntelligence, Nairobi. The redesign is [decision 19](07-decisions.md#19-build-the-map-from-the-systems-and-test-with-the-simulator).

## Buyers

Large organisations and private-equity firms. At a private-equity firm the buyer is the operating partner. Start with one portfolio company, then reuse the same product on a different company. Charge for outcomes.

## Problem

A company cannot safely put agents into its real positions. A generic agent does not follow the org chart, and it cannot act in the systems the company already uses with a sign-off and an audit trail.

## What it does

1. The org chart organises the product. It holds positions, reporting lines, teams, and responsibilities. People fill positions. Nothing is keyed to a named person.
2. Ramonda builds the map from the connected systems and keeps it current. When the company supplies its own org chart, Ramonda compares the two and flags differences. A person is asked only when the sources disagree, or when a change is sensitive. Nobody maintains the map by hand.
3. Access comes from the position. OpenFGA is filled from the map. A change of position changes access. There is no permission rule per person.
4. An agent belongs to a position. It starts at watch, then suggest, then act on routine work. A risky action waits for whoever holds the approving position. Each agent has a manual that a person owns.
5. The same product serves every client. What changes is the systems you connect and the map Ramonda builds. Connectors are written once per system and reused. Ramonda is not forked per client.

## Systems and interfaces

Agents read and write the client's existing systems through Ramonda's gateway. The gateway is the only door. When a person asked, the gateway acts as that person. When nobody asked, it acts as the agent for that position. It never uses a shared credential. Agents never hold credentials.

Staff use Ramonda's web app, and the Rakazo mobile client, to chat, to approve or decline, and to receive alerts. The approval that counts is Ramonda's own step, recorded by the gateway. A Rakazo approval card does not release a write. Email can carry a readable copy. The audit log is the source of truth.

There is no new business dashboard, and no dashboard built for one client. The admin console is for disagreements in the map, connected systems, the audit log, and pausing an agent.

## How it is built

Build the map, the gateway that enforces it, the connectors, and the simulator that tests them. Assemble the rest from mature open source.

Rakazo is the agent runtime and the staff app. It is consumed unmodified. HelixDB stores the map. Helix Foundry drafts the parts of the map it can draft. OpenFGA holds the access check. Identity is Keycloak, or the client's own provider, through OIDC. Secrets sit in OpenBao. Events and the audit stream use Redpanda. An action and its event commit together in Postgres and are relayed to Redpanda. The layout is in [04-architecture.md](04-architecture.md).

Helix Foundry may see a client's real data only with that client's own model key, or with written approval. v0.1 uses simulated data only. That rule is [decision 12](07-decisions.md#12-foundry-sees-real-client-data-only-with-the-clients-approval).

## How a client is tested

The demo company is a simulator. It runs Akwara Cafe, a fictional Nairobi cafe chain, day by day, and writes into the real systems from a business description. It keeps a hidden record of what really happened. Nobody plants the answers. The description is [03-demo-company.md](03-demo-company.md).

Tests are messy questions from people in positions, plus the duties an agent runs when nobody asked. A grader scores them against the hidden record. A surprise event can be injected. A few scripted checks stay as a safety net. `verify/ramonda check 1` is that net for the plumbing that exists today. It is not the product test.

## What ready means

Connect Ramonda to a new company's systems. Nobody writes the org chart or the permissions by hand. Ramonda builds a correct org chart and map. It gives every position the right access. The agents start useful routine work within days.

v0.1 proves that on the simulated cafe, then on a second, different simulated business. The second business is not described yet. It must not be a copy of the cafe.

## Out of scope

Ramonda is not a business-intelligence dashboard and not a data warehouse. It does not replace the client's systems of record. Rakazo is not forked. A new interface is built once and reused. WhatsApp is not a channel. The org chart is not maintained by hand. Permissions are not a table of named people. Test answers are not planted in the systems.
