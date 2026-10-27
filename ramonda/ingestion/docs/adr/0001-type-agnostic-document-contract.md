# One type-agnostic contract, and no code that branches on document type

**Status:** accepted

The manifest hand-assigned a `doc_type` and a `status` per file, and at least one of the two labels was already wrong: CAC49 is a set of Codex session positions, not an `annual_report`. A closed vocabulary means a developer edit for every enterprise and a schema that grows a required field per type. So the contract has one shape for every file: `labels` are an open, multi-valued list of vocabulary terms with a recorded source and confidence, and nothing in chunk, enrich, or retrieval branches on a label. What is genuinely type-specific — a committee code, a standard number, a step number — lives in the `entities` bag until a filter needs one badly enough to promote it to a column.

**Considered options:** a closed enum with per-type required fields (rejected: configuration per type, schema churn on every new corpus); a free-text `doc_type` (rejected: synonym sprawl, unfilterable); a universal core with a typed overlay per document type (rejected: the overlay is the enum again, one level down).

**Consequences:** someone must curate and version the vocabularies, and an empty label list has to be treated as normal rather than as a failure. `status` split in two: the pipeline owns `lifecycle` (discovered → fetched → parsed → chunked → enriched → indexed, or quarantined) and a person owns `review_decision`, which never gates ingestion. That also fixes the field lifecycle: source fields are required, derived fields are optional, are stored keyed by chunk id, and carry `enriched_with`, so a re-chunk can no longer erase an enrichment run the way `chunk.main()` erased the 12 completed chunks.
