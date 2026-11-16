Rust is `core/gateway`, `core/relay`, and `core/outbox`. Python 3.12 connector packages live under `connectors/`. `scripts/seed_akwara_cafe.py` is the one other Python file. TypeScript is `core/console`.

Write the least new code, and take the first rung of the [Ponytail ladder](https://github.com/DietrichGebert/ponytail/blob/main/skills/ponytail/SKILL.md) that fully works.

Folders are the architecture. Comments do not narrate. Done means the feature-map entry was driven and the evidence captured.

| Rule | Enforced by |
| --- | --- |
| Languages have homes. Rust is `core/gateway`, `core/relay`, and `core/outbox`. Python 3.12 connector packages live under `connectors/`. `scripts/seed_akwara_cafe.py` is the one other Python file. TypeScript is `core/console`. | A CI check of tracked paths. A Rust, Python, or TypeScript file outside its home fails that check. The seed script is the exception. Cargo, import-linter, and dependency-cruiser check imports, not where a file sits. |
| Least new code. Take the first rung of the Ponytail ladder that fully works. | `.cursor/rules/ponytail.mdc` and the Ponytail skill. This row is prose. The rows below are checks. |
| Folders are the architecture. | The boundary checks. The error names the folder that may do the job. |
| Comments do not narrate. | The comment check in the lint job. |
| Done means the feature-map entry was driven and the evidence captured. | `verify/feature-map.md` and the `ramonda` CLI. |
