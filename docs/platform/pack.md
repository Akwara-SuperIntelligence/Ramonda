# The Pack

A Pack is all the data that makes the product serve one Tenant. It is a directory of YAML and JSON, validated against schemas, versioned with semver, and it contains no executable code.

To serve a new Tenant you write a new Pack. You do not copy the platform.

## Layout

```
packs/<tenant>/
  manifest.yaml            id, tenant, version, requires_platform, signature
  vocabulary.yaml          the Tenant's Terms: scheme, id, preferred name, synonyms
  document-types.yaml      accepted Document types, Classifications, required Entities
  entities/*.schema.json   JSON Schema for each bag of Entities
  sources.yaml             Sources, Source classes, schedules, mappings
  mappings/*.yaml          how a Source's fields become our fields
  rules/*.yaml             deterministic Rules
  checks/*.yaml            Claims and their two-Source Checks
  workflows/*.yaml         the Tenant's Workflows
  templates/*.md           Artifact templates
  fixtures/*.json          synthetic Runs, one per case worth testing
  tests/*.yaml             expected outcome per fixture
```

## manifest.yaml

```yaml
id: au-reports
tenant: au
version: 1.0.0
requires_platform: ">=0.1 <0.2"
signature: <detached signature over the tree hash>
```

An install fails when `requires_platform` does not match the running image, or when the signature does not verify.

## vocabulary.yaml

Terms are identified by scheme and id, never by a name alone. Two departments naming the same thing differently is a mapping problem, not a reason to edit code.

```yaml
terms:
  - scheme: au/programme
    id: infrastructure
    preferred: "Infrastructure"
    synonyms: ["Infra", "INF"]
```

## sources.yaml

```yaml
sources:
  - id: au-drive
    class: programme-records
    connector: google-drive
    schedule: "0 */6 * * *"
    mapping: mappings/au-drive.yaml
  - id: finance-sharepoint
    class: finance-records      # a different class: it can confirm au-drive
    connector: sharepoint
```

A **Source class** groups Sources that share one upstream failure mode. Two Sources in one class never confirm each other.

## mappings/

```yaml
source: au-drive
document_type: progress-report
classification: internal
fields:
  title:      { from: name }
  issued_at:  { from: modifiedTime, as: timestamp }
  subject:    { from: parents, as: folder_name }
```

## rules/

```yaml
id: missing-budget-figure
when:
  all:
    - { claim: figures.budget_spent, is: missing }
    - { field: subject.programme, eq: infrastructure }
then: { require: human-review, reason: "Finance must supply the figure" }
```

Typed operators only. No loops, no recursion, no user-defined functions. A Rule may call a named function from the approved list and nothing else.

## checks/

```yaml
id: budget-spent
claim: figures.budget_spent
requires:
  classes: [programme-records, finance-records]
  min_sources: 2
compare: predicate            # predicate | exact
on_discrepancy: stop
```

`predicate` compares the Claim, not the number: both Sources answer true or both false. `exact` requires equality after the declared unit conversion. There is no tolerance band and no Source precedence.

## workflows/

See [`workflows.md`](workflows.md). One file per Workflow, each owned by this Tenant.

## templates/

The Artifact's source is markdown. A template names the figures it expects and the sections it needs. A figure missing from the template is not a cosmetic problem: the Run fails.

## fixtures/ and tests/

```json
{ "fixture": "ke-2026-q1", "subject": "ke", "documents": ["ke-q1.txt", "finance-q1.csv"] }
```

```yaml
fixture: ke-2026-q1
expect:
  state: stopped
  discrepancy: budget_spent
```

Fixtures are synthetic. At least one fixture per Workflow must be a deliberate disagreement, because a Pack that has never stopped has never been tested.

## Install

An install validates, in order:

1. every schema is valid;
2. every Workflow names verbs that exist;
3. every Source named belongs to this Tenant, and every Connector exists;
4. every Permission the Workflows need is held by some Role in this Tenant;
5. every template exists;
6. every fixture runs and matches its expected outcome.

Any failure rejects the whole Pack. There is no partial install and no "warnings only".

## Versioning

- A Pack is semver. A change to a Rule's meaning is a major.
- A Run records the Workflow version and the Pack version it started under, and finishes under them.
- An upgrade never retargets a Run in flight.
- An upgrade replays `tests/` before it installs.

## The rule that keeps Packs from becoming code

If a Pack needs behaviour that the seven verbs cannot express, that is a platform change, for every Tenant. Never a step that runs a script. Never a Rule that calls a model. Never an `if tenant ==`.
