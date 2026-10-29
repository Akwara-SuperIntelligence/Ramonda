# The event log is shared infrastructure with its own schema

Status: accepted

The append-only event log is not a module. It has no capability of its own: it records what happened, in order. It lives as shared infrastructure with an `events` schema and a single append API that every module uses. No module reads another module's events as a way to get data.

`jobs` does not own it, because every module needs it and that would make `jobs` the centre of the system. A twelfth module does not own it, because there is no behaviour to own.

## Consequences

- Replay (0024) reads one log, not eleven.
- An event is a fact about the past and is never updated or deleted.
- Reading state always goes through a module's public API; events are for replay and audit, not for querying.
