# Workflows are data

A Tenant's Workflows are files in that Tenant's Pack. Changing what the system does for a Tenant means editing a file, not shipping code.

## What a Workflow is

An ordered list of Steps. Each Step names one verb and gives it inputs. Nothing else.

```yaml
id: quarterly-progress-report
tenant: au
version: 3
trigger:
  schedule: "0 06 1 1,4,7,10 *"
subject: member-state
steps:
  - id: gather
    uses: retrieve
    with:
      query: "quarterly progress {subject} budget"
      sources: [au-drive]
  - id: figures
    uses: extract
    with:
      fields: [budget_released, budget_spent]
      schema: entities/finance.schema.json
  - id: confirm
    uses: check
    with:
      claim: figures.budget_spent
      classes: [programme-records, finance-records]
  - id: write
    uses: draft
    with:
      template: templates/progress.md
  - id: sign
    uses: ask_human
    with:
      role: signer
```

Read it top to bottom. That is the whole control flow.

## The seven verbs

| Verb | Does | Returns |
|---|---|---|
| `retrieve` | finds Chunks by query, inside the Run's scope | Chunks with Anchors |
| `fetch_source` | reads one record from a Source by key | fields |
| `extract` | pulls a value or a statement out of text | value, Anchor, confidence |
| `check` | compares one Claim across two Source classes | `confirmed`, `discrepancy`, or `missing` |
| `draft` | composes the Artifact from a template and confirmed values | an Artifact version |
| `ask_human` | stops and waits for a Person | a resolution or a Signature |
| `escalate` | hands the Run to a Role and ends it | nothing |

Seven is a design limit, not a count. Every verb is code that ships once and serves every Tenant.

## The control flow is one sentence

**A Step either succeeds or the Run stops.**

No loops. No conditionals. No sub-workflows. In v0.1 a `check` that returns `discrepancy` or `missing` stops the Run, because stopping is the product.

If a Tenant needs two paths, that is two Workflows, and a schedule or a Person chooses between them. This is not a gap to close later. It is what makes a Run explainable on one page, which is the thing you are selling.

## What a Workflow may not do

- name a verb that does not exist;
- name a Source that is not this Tenant's;
- name a model;
- hold a secret;
- branch, loop, or call itself;
- exceed the step budget.

Every one of these is checked at install, before a Run exists. A Pack that fails is rejected whole; there is no partial install.

## Why data and not code

Five reasons, in the order they matter:

1. **A Tenant can change it without a release.** A compliance officer can read a Workflow, sign it, and see six months later the exact version that produced an Artifact.
2. **It is diffable.** "What changed between the version that produced this Artifact and today" has an answer.
3. **It is the unit you copy between Tenants.** Code is not.
4. **The engine can refuse a Workflow that names a verb it does not have.** Code can only fail while it runs.
5. **A model in the loop cannot rewrite it.** Models read Documents. They never read or write the Pack.

## Workflows are native to the Tenant

A Workflow belongs to exactly one Tenant. There is no shared library, no base Workflow, no inheritance, no template that upgrades in place.

Two banks may both run a "taxes" Workflow. They are two files that started from the same copy and then diverged. One bank's change is not the other bank's incident. **Copy, never share.**

The consequence, stated plainly: a fix to one Tenant's Workflow does not reach the others. You will feel this as a support cost. It is still cheaper than the alternative, which is one shared definition that must satisfy two compliance teams, two auditors, and two change-control processes at the same time.

Copying is a deliberate human act:

1. copy the directory;
2. change `id` and `tenant`;
3. run the fixtures;
4. install.

There is no `extends`, no `from:`, no registry. If you find yourself building one, you are rebuilding the fork.

## What no-code-per-client actually permits

Exactly one kind of per-Tenant code is allowed: a **Connector**. It reads one Source and hands over Documents, behind one interface:

```python
class Connector(Protocol):
    source_id: str
    def fetch(self, cursor: str | None) -> tuple[list[Incoming], str | None]: ...
```

Rules for it:

- it lives in `connectors/` in this repository, never in a Tenant's Pack;
- it becomes available to every Tenant afterwards;
- it contains reading, never business logic;
- adding one is a release, which is why it is the last resort.

If a Workflow needs something the seven verbs cannot express, that is a platform change: add the verb once, for everyone, and test it with two Tenants. What is never allowed is `if tenant == "au"` inside a verb. The first one is the fork.

## Versioning

`version` is an integer in the file.

- A Run records the Workflow version it started under and finishes under it.
- An upgrade never retargets a Run in flight.
- A Pack install replays that Pack's fixtures first: synthetic Runs with an expected outcome, including at least one deliberately disagreeing Run. A Pack that fails its own fixtures does not install.

## What a Workflow is not

Not an agent. Not a prompt. Not a DAG scheduler. Not a place for a Tenant's code.

The model lives inside `extract` and `draft`, behind a port. The Workflow never names it, never tunes it, and cannot see it.
