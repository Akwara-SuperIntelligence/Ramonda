# A document is identified by its source, versioned by its content, and old versions are superseded rather than deleted

**Status:** accepted

`file_id` was the sanitised filename and a chunk's id was a hash that included its text, so a rename orphaned a document and a single edited paragraph silently invalidated every citation a released report had made. The contract separates the three things that were collapsed into one: `file_id` comes from the source system (`drive:<id>`), so it survives renames and moves; `content_hash` says whether the bytes changed; `version_id` names one immutable state of the content, and every chunk and every citation carries it. A changed file does not overwrite its predecessor: the new version is written and the old one gets `superseded_at`, so a citation made against it still resolves. Chunk ids are deterministic in `(file_id, version_id, anchor, text)`, which makes re-ingestion of unchanged bytes idempotent.

**Considered options:** filename as identity (rejected: rename breaks it, and two folders can hold the same name); delete the old rows on re-ingest (rejected: the row a released citation points at is evidence, and deleting it turns a stale citation into a silent one); a new `file_id` per edit, retaining every version forever (rejected: that is a records-management system, and the source already keeps history — retention is a policy, not a schema).

**Consequences:** retrieval stores more rows and must default its reads to the current version. Pruning superseded versions becomes someone's scheduled job with a per-tenant retention window. Storage cost grows with edit frequency, not with corpus size.
