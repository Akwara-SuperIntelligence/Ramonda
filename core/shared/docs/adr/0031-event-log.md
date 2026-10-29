# The event log is shared infrastructure with its own schema

Status: accepted

The append-only event log is not a module. It has no capability of its own: it records what happened, in order. It lives as shared infrastructure with an `events` schema and a single append API that every module uses. No module reads another module's events as a way to get data.

`jobs` does not own it, because every module needs it and that would make `jobs` the centre of the system. A twelfth module does not own it, because there is no behaviour to own.

**Amended by 0053.** The append call is still the only write into the log, but a module no longer makes it from its own request path. The module writes its event to an outbox in its own schema, in the same transaction as the state change, and a relay hands it to shared. The `events` schema remains shared's, and no module reads it except through replay.

## Consequences

- Replay (0024) reads one log, not eleven.
- An event is a fact about the past and is never updated or deleted.
- Reading state always goes through a module's public API; events are for replay and audit, not for querying.
