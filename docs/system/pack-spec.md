# Pack specification

A Pack is the data that makes the platform serve one use case for one client. It is a git repository of YAML and JSON, validated against JSON Schema, signed, and versioned with semver. It contains no executable code.

To serve a new client you write a new Pack. You do not copy the platform.

## Layout

```
packs/<client>/
  manifest.yaml            id, version, app-schema range, signature
  vocabulary.yaml          the client's Terms: scheme, id, preferred name, synonyms
  document-types.yaml      accepted document types, Classifications, required Entities
  entities/*.schema.json   JSON Schema for each Entity bag
  sources.yaml             Sources, Source classes, schedules
  mappings/*.yaml          how a Source's fields become our fields
  rules/*.yaml             deterministic Rules
  checks/*.yaml            Claims and their two-Source Checks
  decision.yaml            outcome list, required fields, escalation targets
  templates/disposition.md report template
  fixtures/*.json          synthetic cases, generated from the schemas
  tests/*.yaml             expected outcome per fixture; run on every install
```

## manifest.yaml

```yaml
id: baraka-aml
version: 1.4.0
requires_app_schema: ">=1.0 <2.0"
client: Baraka Commercial Bank
signature: <detached signature over the tree hash>
```

An install fails if `requires_app_schema` does not match the running Cell, or if the signature does not verify.

## sources.yaml

```yaml
sources:
  - id: core-ledger
    class: ledger              # Source class, see below
    connector: postgres-t24
    schedule: "*/15 * * * *"
  - id: screening-vendor
    class: screening
    connector: http-json
  - id: analyst-search-log
    class: screening           # same class: same upstream, so it cannot corroborate
```

A **Source class** groups Sources that share one upstream failure mode. Two Sources in one class never corroborate each other. This is the rule that stops a Check from passing on two copies of the same error.

## rules/

```yaml
id: large-amount-review
when:
  all:
    - { claim: alert.amount_above_threshold }
    - { field: subject.risk_rating, eq: high }
then: { require: human-review, reason: "Policy 7.2" }
```

Rules are data: typed operators, no loops, no recursion, no user-defined functions. A Rule may call a named function from the approved list (`fx.convert`, `window.sum`) and nothing else. See `adr/0004`.

## checks/

```yaml
id: alert-amount
claim: alert.amount_above_threshold
requires:
  classes: [monitoring, ledger]   # at least one Source from each
  min_sources: 2
compare: predicate                # predicate | exact
on_discrepancy: stop
```

`predicate` compares the Claim, not a raw number: both Sources must answer true, or both false. `exact` requires equal values after the declared unit conversion. There is no tolerance band, and no Source is ever preferred over another. See `adr/0007`.

## decision.yaml

```yaml
outcomes:
  - suspicious
  - routine
  - escalate-to-mlro
required_fields: [rationale, rule_trail, evidence_bundle]
escalation: { queue: mlro-review, notify: email }
```

## Versioning and install

- A Pack is semver. A breaking change to a Rule's meaning is a major.
- A Case records the Pack version it opened under and is judged only by that version.
- An upgrade must replay `tests/` green **before** it installs.
- An upgrade never retargets a Case in flight; in-flight Cases finish on the old version.
- Fixtures are generated from the schemas in this Pack, so a fixture that will not load is a broken Pack.

## The template

`packs/aml-bank/` is the worked example: copy it, rename it, and replace the contents. Starting a client is copying a known-good Pack, not remembering what a Pack contains. Files a Pack may carry but this one does not yet (in `pack-spec.md` above) are added when the first client needs them.
