# Replay reads the log through one narrow, subject-scoped call

Status: accepted

Shared exposes one read: the envelopes for a subject, ordered by sequence, over a range. `artifacts` uses it to rebuild an Artifact Version, `jobs` uses it to orchestrate a replay. Shared returns envelopes and interprets nothing.

The read is subject-scoped because 0031 forbids reading events as a way to get data: a module can reconstruct the history of one work item and cannot browse the log. Modules do not open the log with SQL; the schema stays shared's, and the shape does not leak into eleven modules.

A human-facing history is an audit screen built on this same call. That changes who is shown the history, not who may read it.

## Consequences

- Replay reads the log, object storage for exported files and archived pages, and the owning modules' public APIs for current state.
- A module that needs another module's facts for replay reads them from the log, not from that module's tables.
- The read returns envelopes, so a caller that wants typed data decodes the payload itself. The alternative — shared decoding payloads — would require shared to know what a Run or an Artifact is.
