# A long document is built by map over its items, with a bounded context per section

Status: accepted

A hundred-page document cannot be drafted in one context window, and it must not be attempted. The document is built as follows.

**State lives in the database, not the context.** The outline, every section's current draft, the evidence ledger and a rolling digest are stored per job. A specialist receives only what its section needs.

**Fan out per item.** Each Agenda Item is independent work. Items are dispatched in parallel, and within an item the sections may also run in parallel.

**Bound the context.** Each section's bundle is assembled by code with a token budget: the Structure Spec for that section, the item's objects, the top-ranked passages for that item, the evidence records, the client's style rules, and the document digest. Nothing else.

**Coherence reads the digest, not the text.** A coherence pass compares section headers, positions and recurring claims against each other, which catches contradiction without loading the whole document.

**Assembly is deterministic.** Sections are written into the Structure Spec's positions and exported as DOCX by code, never by the model.

**Rebuild is incremental.** Changing one item re-runs that item's specialists only. Retrieval results, embeddings and archived pages are cached and reused.

**The editor streams.** Sections appear as they are completed, so the Author starts reviewing while the rest is still building.

## Consequences

- Wall-clock time scales with the slowest item, not with the sum of all items.
- Cost and latency are governed by the token budget per section, which is a number we can set and tune.
- A document can be partially regenerated without touching sections that did not change.
