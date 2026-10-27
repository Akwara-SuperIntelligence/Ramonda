# Documents: source identity, immutable versions, one block model, real anchors

Inherited from the previous system, kept because it was right and because it is the foundation of the traceability claim.

- **Identity comes from the Source**, never the filename: `(source_id, source_ref)` is unique. A rename is not a new Document.
- **A Document version is immutable and identified by its content hash.** A citation names a version. A replaced version is superseded, never deleted, so old citations still resolve.
- **Every parser produces one Block model** — heading, paragraph, list item, table, figure — so chunking never depends on the format. Formats we cannot parse go to Quarantine with a reason; they are never dropped silently.
- **One Anchor per Chunk**: section, paragraph, the printed page only where the document has pages, plus a frozen Quote so a moved Anchor is detectable. A `.docx` gets no page number, because inventing one is worse than omitting it.
- **Picture text is Evidence about a picture, never the document's prose**, and no number is a fact without a named dataset or a confirming Source.

The previous implementation drifted from these rules — three chunk-id schemes, a closed `doc_type` that rejected real files, retrieval that did not match the contract. The rewrite keeps the rules and makes them compile-checked: one `Chunk` type, serialised into the index from the same struct, so index and contract cannot disagree.
