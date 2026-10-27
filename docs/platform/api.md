# The API

The API is the product. Our own review page is only a client of it, and there are no private endpoints for it.

Base path `/v1`. Additive changes only inside a version. A breaking change is a new major path.

## Authentication

`Authorization: Bearer <jwt>`, verified against the Tenant's JWKS, issuer and audience. Fail closed.

The Tenant comes from the token. **A request body or query that carries a Tenant id is rejected with `400`.** Connectors use a workload identity, never a Person's token.

## Resources

### Who am I

```http
GET /v1/me
→ { tenant, person, roles: [...], permissions: ["workflow:run:quarterly-progress-report", "artifact:sign"] }
```

The UI uses this to hide what a Person cannot do. The server never trusts it.

### Documents

```http
POST /v1/documents            # multipart, or a Source reference
→ 202 Accepted, Location: /v1/documents/{id}
GET  /v1/documents?cursor=
GET  /v1/documents/{id}
POST /v1/documents/{id}/review  # a Person's decision to allow or block use
→ 201
```

A Document in Quarantine returns `422` with the reason, never a silent omission.

### Runs

```http
POST /v1/runs
{ "workflow": "quarterly-progress-report", "subject": "ke" }
Idempotency-Key: ...
→ 202 Accepted, Location: /v1/runs/{run_id}

GET  /v1/runs/{run_id}
→ { state, workflow_version, started_at, stopped_reason? }

POST /v1/runs/{run_id}/stop
→ 202                     # sets cancel_requested; checked at every Step boundary

GET  /v1/runs/{run_id}/steps
→ [{ step, verb, state, started_at, duration_ms, tokens, cost_minor }]

GET  /v1/runs/{run_id}/discrepancies
→ [{ claim, left: {value, anchor, source}, right: {...} }]

POST /v1/runs/{run_id}/resolve
{ "claim": "budget_spent", "chosen": "finance-records", "note": "..." }
→ 202
```

`state` is one of `queued | running | waiting_for_human | stopped | drafted | escalated | failed`.

`stopped` returns its Discrepancies in the same call, so the UI renders both values without a second round trip.

### Artifacts

```http
GET  /v1/artifacts/{id}                   # the current version
GET  /v1/artifacts/{id}/versions
GET  /v1/artifacts/{id}/versions/{n}
POST /v1/artifacts/{id}/sign  { version, note }
→ 201 { signature_id, signed_at, principal }

GET  /v1/artifacts/{id}/explain?value=figure:budget_spent
→ { value, anchor: {document_version, page, quote}, sources: [...], rule_version, trace_id }
```

`explain` is the page a Person reads when a regulator asks why. It returns the Anchor, the two confirming Sources, the Rule version and a link to the Trace.

### Evidence

```http
GET /v1/evidence/{id}
GET /v1/evidence/export?run_id={id}
→ 200, a signed bundle: every value, its Anchor, the Source that confirmed it, the Rule version, and every Signature
```

## Conventions

- **Errors** are `application/problem+json` (RFC 9457) with a stable `code`, a human `detail`, and a `trace_id`. Never a bare 500, never a message that leaks another Tenant's data.
- **Idempotency**: every `POST` that creates or changes state requires `Idempotency-Key`. A replay returns the original response.
- **Pagination** is cursor-based: `?limit=&cursor=`, stable order by `(created_at, id)`. No offsets.
- **Long work** returns `202` and a `Location`.
- **Money** is `{ "amount_minor": 5000000, "currency": "KES" }`. Never a float.
- **Time** is RFC 3339, UTC.
- **Identifiers** are opaque. Clients do not parse them.
- **Enums** may gain values. A client tolerates an unknown value instead of crashing.
- **Observability**: every response carries `x-request-id`; every log line carries `trace_id` and `run_id` where they exist.
- **OpenAPI** is generated, committed as a release artifact, and CI fails when the committed file differs from the generated one.

## What a client must be able to do on day one

1. Push a Document, or list what a Connector collected.
2. Start a Run for a Workflow and a Subject.
3. Stop a Run.
4. Receive `drafted`, `stopped` or `escalated`.
5. Read a draft with every figure linked to an Anchor.
6. Resolve a Discrepancy.
7. Sign an Artifact version.
8. Export the Evidence for one Run.

If a screen in our own UI needs something that is not on this list, the API is wrong, not the UI.
