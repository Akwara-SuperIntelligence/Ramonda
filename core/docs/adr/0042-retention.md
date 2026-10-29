# Retention is a per-client policy with a floor, and deletion is an event

Status: accepted

Default: documents and evidence kept seven years, event log ten years, cold storage after one year. The policy is client configuration because it follows the client's regulator, with a five-year floor beneath which it cannot be set.

Nothing is deleted except under a named legal-hold exception, and the exception itself is an event. Append-only and deletion are opposites, so the only way to honour both is to make deletion auditable.

## Consequences

- Retention is a configuration surface per deployment, not a constant in code.
- A client with a longer statutory period raises the number; nobody lowers it below the floor.
- Cold-tiering is automatic and reversible; purging is manual, named and logged.
