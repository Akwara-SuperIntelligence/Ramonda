# The event log is one hash chain per deployment

Status: accepted

Each event stores `prev_hash` and `hash`, where the hash is computed over the event's canonical bytes and includes `prev_hash`. The first event chains from a fixed genesis value. The head is the last event's hash, and 0041's signature covers it — which is what turns "the log has not changed" into a checkable claim instead of a promise.

Appends serialise on the head: the relay holds the head row's lock, computes the hash, inserts, and releases. Several relay loops therefore queue at one row. That is affordable because events are written per Run and per state change, not per request, and a deployment is a small office.

A per-Job chain was rejected. It attests that Job's events and leaves the rest of the log unattested, so 0041's "event-log head" would mean less than it says.

## Consequences

- Verification walks the chain from genesis to head and needs every event, including cold-tiered ones. Retention moves bytes, and never removes them from the chain.
- The canonical byte form is part of the contract: two writers must produce the same hash for the same fact. It is fixed in `MODULE.md`, not left to each module.
- One writer at the head bounds append throughput to one row lock. That is the first number to measure if events ever lag.
