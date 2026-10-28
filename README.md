# Ramonda v0.1

One product that runs an enterprise's own document workflows. It reads Documents, pulls out figures and statements, applies the enterprise's written Rules, and will not let a figure through unless a second Source confirms it. When two Sources disagree, the Run stops and a Person sees both values.

One repository. One image. One database per Tenant. A Workflow is a Tenant's own data, so a new Tenant costs a Pack, not a fork.

**Status: v0.1, design only.** There is no application code in this repository yet, on purpose. The first code lands when the first Pack exists to run.

## Read in this order

| File | Answers |
|---|---|
| [`GLOSSARY.md`](GLOSSARY.md) | what the words mean |
| [`docs/platform/architecture.md`](docs/platform/architecture.md) | the shape, the six modules, the runtime |
| [`docs/platform/workflows.md`](docs/platform/workflows.md) | what changes per Tenant, and why it is data |
| [`docs/platform/pack.md`](docs/platform/pack.md) | what is inside a Pack |
| [`docs/platform/api.md`](docs/platform/api.md) | the public surface |
| [`docs/platform/releases.md`](docs/platform/releases.md) | how code reaches a Tenant |
| [`docs/platform/harness.md`](docs/platform/harness.md) | the loop, and what we adopt |
| [`docs/platform/security.md`](docs/platform/security.md) | what can go wrong, and the controls |
| [`docs/platform/evaluation.md`](docs/platform/evaluation.md) | how we know a Run is right |
| [`docs/adr/ADR.md`](docs/adr/ADR.md) | the twelve decisions that are hard to reverse |

## The claim in one sentence

A figure reaches an Artifact only with an Anchor to the page it came from, a second Source that confirms it, the Rule version that judged it, and a Person who signed it.

Everything else in these documents exists to make that sentence true, or to make it cheap to repeat for the next Tenant.

## What is not here

No client Packs, no code, no migrations. The first Pack is the real test of the design, and it does not exist yet.
