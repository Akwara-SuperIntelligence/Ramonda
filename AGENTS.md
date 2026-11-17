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
