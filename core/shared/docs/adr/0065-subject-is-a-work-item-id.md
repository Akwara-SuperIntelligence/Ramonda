# A subject is a work-item id, or nothing

Status: accepted

Each event carries a subject: the id of the work item the fact belongs to. The subject is opaque to shared — a string. Replay reads by subject (0057), and only a work-item fact needs one.

A system fact has no subject. A key rotation, a partition retirement and a relay failure are about the deployment, not about work, and the field stays empty. A synthetic subject such as `system` was rejected because it invites unrelated facts to be grouped and later read as one history. A typed subject reference was rejected because nothing asks a second question of it.

## Consequences

- `subject` is nullable, and the only read is by subject.
- The modules agree on what a subject points at. Shared never checks it.
- A work-item fact with no subject is a bug, and the module that wrote it owns it.
