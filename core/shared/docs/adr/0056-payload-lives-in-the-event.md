# A model output is stored in the event itself

Status: accepted

The model output, the tool result and the other bulk fields live in the event's payload, in Postgres. They are not moved to an object store.

The outbox decides this. 0053 requires the event and the state change to commit in the module's own transaction, so the payload is in that row before the relay ever runs. Uploading it to storage first would add a second system, a failure window and orphaned objects, and would not make the outbox row smaller.

At v0.1's scale the numbers are small. A forty-item document is a few hundred model calls, a few megabytes per Job, and ten years of a two-person desk is measured in gigabytes. Postgres stores that without strain, and a log that reads fast is worth more than a log with small rows.

A storage reference can be added later as a new payload field for selected events, without changing the chain or the reader.

## Consequences

- The audit record itself is in Postgres, so backing up and restoring the record is one operation.
- The revisit trigger is explicit and measured: one payload over 1 MB, or the log past 100 GB. Not a hunch, not a style preference.
- Exported files (DOCX, PDF) and archived pages still live in object storage (0014). This decision is about the event's own content, not every byte the system touches.
