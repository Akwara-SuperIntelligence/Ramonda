# Shared holds primitives, not policy

Status: accepted

The v0.1 inventory of shared, and the line that produced it.

**In shared:**

- the event log
- object storage
- the model transport
- the egress-bound HTTP client
- the clock
- ID generation
- database sessions, database roles and the migration runner
- key access, and the sign and verify primitive
- the durable queue
- observability: logs, numbers and traces about the machine

**Not in shared:**

- client configuration and the composition file — the shell loads them (0047)
- the fetch-and-archive service — it is a behaviour that produces a snapshot, so `sources` and `evidence` own it (0014)
- caching, mail and the metrics backend

The line is this. Shared decides where bytes go, what time it is, how a call leaves the box, how work waits, and where a fact about the machine is written. It does not decide what to fetch, what a Run means, when to purge, what to enqueue, or what to alert on.

Observability is in shared because the requirement is to monitor the system as a whole, and no single business module owns the whole. Shared gives the line and the number; the decision about what is worth measuring stays with the caller and the deployment.

## Consequences

- A shared primitive that begins to decide something has become a module (0049).
- Anything in the "not in shared" list needs an owner before it is built. None of them is shared.
- Observability and the event log are different things and get different stores and different lifetimes: the log is append-only evidence with a ten-year retention, observability is deletable machine output that never carries client content.
