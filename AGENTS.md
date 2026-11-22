Rust is `core/gateway`, `core/relay`, and `core/outbox`. Python 3.12 connector packages live under `connectors/`. `scripts/seed_akwara_cafe.py` is the one other Python file. TypeScript is `core/console`.

Write the least new code, and take the first rung of the [Ponytail ladder](https://github.com/DietrichGebert/ponytail/blob/main/skills/ponytail/SKILL.md) that fully works.

Folders are the architecture. Comments do not narrate. Done means the feature-map entry was driven and the evidence captured.

| Rule | Enforced by |
| --- | --- |
| Languages have homes. Rust is `core/gateway`, `core/relay`, and `core/outbox`. Python 3.12 connector packages live under `connectors/`. `scripts/seed_akwara_cafe.py` is the one other Python file. TypeScript is `core/console`. | A CI check of tracked paths. A Rust, Python, or TypeScript file outside its home fails that check. The seed script is the exception. Cargo, import-linter, and dependency-cruiser check imports, not where a file sits. |
| Least new code. Take the first rung of the Ponytail ladder that fully works. | `.cursor/rules/ponytail.mdc` and the Ponytail skill. This row is prose. The next three rows are checks. |
| Folders are the architecture. | The boundary checks. The error names the folder that may do the job. |
| Comments do not narrate. | The comment check in the lint job. |
| Done means the feature-map entry was driven and the evidence captured. | `verify/feature-map.md` and the `ramonda` CLI. |
| The second time CodeRabbit or a reviewer flags the same kind of problem, add or extend a lint or static check so CI enforces it. | That check, from then on. Until it lands, this row is prose. |
| Gateway auth and permissions, database migrations, and deployment need @Hassan-KreateStudio to approve before merging. Agents flag those PRs in the description. | The owner, @Hassan-KreateStudio. This row is prose. |
| Every ticket is worked in the style of the pstack `poteto-mode` skill. Before saying done, apply `principle-prove-it-works` (run the real thing and capture the evidence). PRs that touch gateway auth and permissions, database migrations, or deployment also run the pstack `blast-radius` skill and put its findings in the PR description. | The pstack plugin skills. This row is prose. |

## Plans, specs and tickets live in Linear

Specs, plans, decisions, and tickets live in the [Akwara workspace](https://linear.app/akwara-hq). Tickets are in the Ramonda team (key RAM). GitHub issues are not used for planning.

Read the relevant Linear doc and the ticket (RAM-n) before starting. Name that RAM ticket in the PR description so GitHub links it.

Projects: [0. Ramonda overview and reference](https://linear.app/akwara-hq/project/0-ramonda-overview-and-reference-9e8dc09c81d1), [1. Simulator](https://linear.app/akwara-hq/project/1-simulator-4de458bbcbba), [2. Map steward](https://linear.app/akwara-hq/project/2-map-steward-7dab95bb8206), [3. Position-based access](https://linear.app/akwara-hq/project/3-position-based-access-262937e1451d), [4. First position agents](https://linear.app/akwara-hq/project/4-first-position-agents-6c5f181ffb94), [5. Second business (logistics)](https://linear.app/akwara-hq/project/5-second-business-logistics-9780e3dd0bcc).

Docs: [Product brief](https://linear.app/akwara-hq/document/ramonda-v01-product-brief-e338d72b5aca), [PRD](https://linear.app/akwara-hq/document/ramonda-v01-product-requirements-prd-8891c38f5804), [Akwara Cafe, the simulator](https://linear.app/akwara-hq/document/ramonda-v01-akwara-cafe-the-simulator-ca85c105a7af), [Architecture](https://linear.app/akwara-hq/document/ramonda-v01-architecture-fce12b302e80), [Security model](https://linear.app/akwara-hq/document/ramonda-v01-security-model-775c99b29a99), [Ontology](https://linear.app/akwara-hq/document/ramonda-v01-ontology-what-the-map-holds-6fbd8352129e), [Decisions log](https://linear.app/akwara-hq/document/ramonda-v01-decisions-log-817852748b33), [Build plan](https://linear.app/akwara-hq/document/ramonda-v01-build-plan-bcc05dff0daa).
