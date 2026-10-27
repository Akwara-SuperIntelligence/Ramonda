# Ingestion contract

**Status:** accepted. **Scope:** intake → parse → chunk → enrich → picture text. Retrieval's ranking and storage and the agent's behaviour are out of scope; this contract only says what a document, a chunk, and a figure are.

The contract has four parts: the fields of the three records, the invariants that bind them, the chunking rules the chunker must follow, and the citation grammar that follows from the anchors. `ramonda/ingestion/contract.py` carries the same field lists and vocabularies and is the checkable copy. The two cannot drift: the module's self-check reads this file.

## How to read this

**Three records.** A `Document` is the unit of identity, version, access, and provenance. A `Chunk` is a retrievable piece of it with exactly one anchor. A `Figure` is a picture and the claims attached to it. A chunk never exists without its document; a figure never exists without the chunk that carries it.

**Two field classes.** A **source field** is read from the bytes or the source system. A **derived field** is produced by a model or a rule, may be absent, and is never authoritative. Derived fields record `enriched_with` (`model`, `prompt_version`, `at`), and their absence is a normal state, not an error. A re-chunk must never destroy derived work: derived fields are stored keyed by chunk `id`, so an unchanged chunk keeps its enrichment.

**Nothing is configured per document type.** A new format is supported when a parse adapter claims it (ADR 0003). A new kind of document is a new `labels` term, not a new field and not a branch in code (ADR 0001). The required fields below are exactly the fields any format can produce.

## Document fields

| Field | Type | Required | Class | Notes |
|---|---|---|---|---|
| `org_id` | string | yes | source | The tenant. Part of every key. |
| `file_id` | string | yes | source | `<source_system>:<source_id>`. Survives rename and move. |
| `version_id` | string | yes | source | The source's immutable version token when it has one, otherwise `content_hash`. |
| `content_hash` | string | yes | source | SHA-256 of the bytes. Detects change and deduplicates; it is not an identity. |
| `previous_version_id` | string | no | source | The version this one replaced. |
| `superseded_at` | timestamp | no | pipeline | Set when a newer version exists. The row is kept, not deleted (ADR 0002). |
| `source_system` | string | yes | source | e.g. `drive`, `sharepoint`. |
| `source_id` | string | yes | source | The id inside that system. |
| `source_url` | string | no | source | Where a reader can open the original. |
| `mime_type` | string | yes | source | The sniffed type, not the extension and not the declared type. |
| `title` | string | no | derived | Recorded with `title_source`. A filename is the last resort, not the first. |
| `title_source` | enum | with title | derived | `embedded-metadata`, `filename`, `model`. |
| `published_at` | date | no | source | When it appeared. One point in time. |
| `coverage_start` | date | no | source | Start of the period the document is about. |
| `coverage_end` | date | no | source | End of that period. A July-to-July report runs 2025-07-01 to 2026-06-30; it is not "year 2026". |
| `language` | string | no | derived | BCP 47. |
| `labels` | term[] | no | source or derived | Open and multi-valued. An empty list is valid and means unclassified. |
| `lifecycle` | enum | yes | pipeline | See Lifecycle. A pipeline value; never set by a person. |
| `quarantine_reason` | string | when quarantined | pipeline | The failure in words. Required when `lifecycle` is `quarantined`. |
| `review_decision` | enum | no | human | `approved` or `rejected`; absence means unreviewed. Gates use, never ingestion. |
| `reviewed_by` | string | with review | human | Who decided. An approval with no name is not an approval. |
| `reviewed_at` | timestamp | with review | human | When. |
| `security_label` | enum | yes | source | `public`, `internal`, `confidential`, `restricted`. No default: access that cannot be mapped quarantines. |
| `access` | subject[] | yes | source | `user:<id>` or `group:<id>`. An empty list means nobody. |
| `department` | string | no | source or derived | Not truth unless the source says so. A derived department carries its source like any derived field. |
| `parser` | string | no | pipeline | The adapter that produced the blocks. |
| `parser_version` | string | no | pipeline | |
| `parser_strategy` | string | no | pipeline | e.g. `fast`, `hi_res`, `docling-md`. |
| `parse_warnings` | string[] | no | pipeline | A partial parse is not a failure; record what was missed. |

## Chunk fields

| Field | Type | Required | Class | Notes |
|---|---|---|---|---|
| `id` | string | yes | derived | `hash(file_id, version_id, anchor, text)`. Unchanged content keeps its id across re-ingestion. |
| `org_id` | string | yes | copy | Must equal the document's. |
| `file_id` | string | yes | copy | Must equal the document's. |
| `version_id` | string | yes | copy | Must equal the document's. A citation names it. |
| `kind` | enum | yes | source | `text` or `table`. Closed. Picture text is `text`, never a third kind. |
| `text` | string | yes | source | Verbatim content, never the breadcrumb. A table's text is HTML, optionally preceded by its caption line. |
| `breadcrumb` | string | yes | source | The section, root first, joined by ` > `. May be empty when the document has no headings. |
| `anchor_paragraph_start` | int | text chunks | source | 0-based within the section. |
| `anchor_paragraph_count` | int | text chunks | source | How many blocks the chunk spans. |
| `anchor_row_start` | int | table chunks | source | 0-based data row; the header row is not counted. |
| `anchor_row_count` | int | table chunks | source | |
| `anchor_page` | int | no | source | The number printed on the page. Never a synthetic page. |
| `anchor_quote` | string | yes | derived | About 80 characters from the start of `text`, frozen so a stale anchor is detectable. |
| `derived_from` | enum | yes | pipeline | `body`, `table`, `figure`, `caption`. |
| `figure_ref` | string | with figure | pipeline | The `figure_id` this chunk came from. Required when `derived_from` is `figure` or `caption`. |
| `parser` | string | no | pipeline | Only when it differs from the document's. |
| `security_label` | enum | yes | copy | Must equal the document's. |
| `access` | subject[] | yes | copy | Must equal the document's. A cache, rebuilt on every save. |
| `document_title` | string | no | copy | Equal to the document's `title` when both exist; it is what a citation prints. |
| `section_summary` | string | no | derived | |
| `prev_section_summary` | string | no | derived | |
| `excerpt_keywords` | string | no | derived | Free text. Identifiers are not this field; they are `entities`. |
| `questions` | string | no | derived | Retrieval stores this as `questions_this_excerpt_can_answer`. |
| `entities` | term[] | no | derived | Typed terms, not strings. The open bag where type-specific facts live. |
| `enriched_with` | object | with any enriched field | pipeline | `model`, `prompt_version`, `at`. Covers `section_summary`, `prev_section_summary`, `excerpt_keywords`, `questions`, `entities`. |

## Figure fields

| Field | Type | Required | Class | Notes |
|---|---|---|---|---|
| `figure_id` | string | yes | derived | `hash(file_id, version_id, figure anchor)`. |
| `org_id` | string | yes | copy | Must equal the document's. |
| `file_id` | string | yes | copy | Must equal the document's. |
| `version_id` | string | yes | copy | Must equal the document's. |
| `chunk_id` | string | yes | derived | The chunk that carries this figure. |
| `figure_label` | string | no | source | The label the document prints, e.g. `Figure 3`. |
| `caption` | string | no | source | |
| `image_ref` | string | no | pipeline | Where the image bytes are kept. |
| `anchor_page` | int | no | source | The printed page. |
| `bbox` | number[] | no | pipeline | Only when the parser supplies one. |
| `chart_type` | string | no | derived | |
| `axis_labels` | string[] | no | derived | |
| `series` | string[] | no | derived | |
| `values` | value[] | no | derived | Each entry carries its own `source`. |
| `dataset_citation` | object | with dataset values | source | `dataset`, `domain`, `item`, `area`, `year`, `accessed`, `url`, `licence`. |
| `extractor` | object | with any derived field | pipeline | `name`, `version`, `prompt_version`. |
| `review_decision` | enum | no | human | A person confirming the figure's values. |

### Term reference

`labels` and `entities` share one shape, so that a vocabulary can be versioned as data rather than as code.

| Field | Type | Required | Class | Notes |
|---|---|---|---|---|
| `scheme` | string | yes | source | The vocabulary, with its version. e.g. `codex-committees@1`. |
| `term_id` | string | yes | source | Canonical id inside the scheme. Facets filter on this, never on the label. |
| `label` | string | no | derived | What a person reads. Synonyms are the query analyzer's problem, not a stored value. |
| `confidence` | number | no | derived | From the proposer. Calibration is the proposer's problem. |
| `source` | enum | yes | source | `folder`, `filename`, `embedded-metadata`, `model`, `human`. |
| `evidence` | string | no | derived | The text that prompted the term. |

## Invariants

**I1 — Content, not context.** A chunk's `text` never contains its `breadcrumb`. The form that is embedded is `breadcrumb + "\n\n" + text`; the form that is cited and stored is `text`.

**I2 — One section.** A chunk belongs to exactly one section and never spans two. `breadcrumb` is that section.

**I3 — One anchor.** A text chunk carries a paragraph range, a table chunk a row range, and every chunk carries `anchor_quote`, which must appear in `text`.

**I4 — Printed pages only.** `anchor_page`, when present, is the number printed on the page. A synthetic page — characters divided by some page size — is forbidden. A `.docx` has no pages; it gets no page.

**I5 — Two kinds.** `kind` is `text` or `table`. Picture text is `text` with `derived_from` set. No new kind is added for a new format.

**I6 — Picture text is evidence about a picture.** A chunk with `derived_from` of `figure` or `caption` is never the document's own prose and never the source of a number stated as fact (ADR 0005).

**I7 — No number without a dataset.** A number may be stated as fact only from a figure record value whose `source` is `dataset` and which carries a `dataset_citation`. `label_ocr` and `vlm_estimate` values are recorded claims, not facts.

**I8 — Access is the document's.** `security_label` and `access` exist once, on the document. The chunk's copies must equal the document's. The copy is a cache and is rebuilt on every save, so a permission change forces a re-save.

**I9 — Derived is optional and attributed.** A derived field is never required. A chunk's enriched fields — `section_summary`, `prev_section_summary`, `excerpt_keywords`, `questions`, `entities` — are covered by `enriched_with`, and a chunk carrying any of them must have it. The title carries `title_source` instead, because a title is read rather than generated.

**I10 — Deterministic ids.** The same file, version, anchor, and text always produce the same chunk `id`; changing any of them produces a different one. Re-running a parse over unchanged bytes is idempotent.

**I11 — No state it has not reached.** `lifecycle` only ever moves forward. A `quarantined` document has no chunks and carries `quarantine_reason`.

**I12 — Metadata is never a gate.** Intake requires only `org_id`, `source_system`, `source_id`, and bytes. Missing title, type, year, or status never rejects a document; they produce empty fields. The manifest is a seed, not a gate.

## Chunking rules

The chunker is type-agnostic: these rules apply to a 54-page report and to a 2,000-page transcript alike.

1. **Split on structure first.** Never cross a heading. Group the blocks of one section into chunks at paragraph boundaries, in document order.
2. **Target 500 tokens**, measured with the embedding model's tokenizer, with a hard ceiling of 800. A chunk below 80 tokens merges into its neighbour in the same section.
3. **No overlap** while paragraph boundaries can be respected. Where a single block exceeds the ceiling, split at sentence boundaries with up to 15% overlap.
4. **Tables stay whole** up to 2,000 tokens, caption line included. Beyond that, split by groups of rows, repeat the header row in every chunk, and never split mid-row. A short row range is still its own chunk; a table's value is in its totality.
5. **Figures get one chunk each.** Its text is the caption followed by whatever the picture's OCR recovered. The values, if any, live in the figure record, never in the chunk text.
6. **Deduplicate within a document** by `(kind, text, breadcrumb)`; the same block read twice is one chunk. Never deduplicate across documents.
7. **A chunk is only built from blocks.** Text that exists in no block (a header, a footer, a page number) never becomes a chunk.

## Lifecycle

| State | Meaning | Set by |
|---|---|---|
| discovered | The source system lists it; no bytes yet. | pipeline |
| fetched | Bytes and source fields are in hand. | pipeline |
| parsed | Blocks exist for this version. | pipeline |
| chunked | Chunks exist for this version. | pipeline |
| enriched | Derived fields were attempted for every chunk; some may be empty. | pipeline |
| indexed | Retrieval accepted every chunk. | pipeline |
| quarantined | It cannot be parsed or its access cannot be mapped. | pipeline, with a reason |

`review_decision` is orthogonal: a document can be indexed and unreviewed, or reviewed and quarantined. Review gates use by the agent, never ingestion. A re-ingest of a changed file moves to a new `version_id` and starts again at `fetched`; the previous version keeps its rows with `superseded_at` set.

## Citation grammar

A citation is assembled from the anchor, and each form may only claim what its evidence supports.

| Evidence | Citation | May claim |
|---|---|---|
| text chunk | `<document_title or file_id>, §<breadcrumb>, ¶<anchor_paragraph_start + 1>[, p.<anchor_page>]` | What the report says, at that position. |
| table chunk | `<document_title>, §<breadcrumb>, rows <start>–<end>[, p.<page>]` | What the table lists. |
| figure chunk | `<document_title>, <figure_label or "figure">, §<breadcrumb>[, p.<page>]` | What the figure shows; ordering and trend, not exact values. |
| dataset value | `<document_title>, <figure_label>, from <dataset_citation.dataset> (<accessed>)` | The number itself, at the dataset's precision. |

Omit `§` when `breadcrumb` is empty. A citation never cites a chunk id, a file path, or a page that the document does not print.

## What this changes in retrieval

Retrieval is out of scope, but the contract cannot land on today's schema without these changes. They are listed so the migration is a known piece of work, not a surprise.

- `retrieval.chunk` gains `version_id`, `derived_from`, `figure_ref`, `anchor_page`, `anchor_paragraph_start`, `anchor_paragraph_count`, `anchor_row_start`, `anchor_row_count`, `anchor_quote`, `entities`, and `enriched_with`. `kind` keeps its `('text','table')` check, unchanged.
- `retrieval.document` gains `version_id`, `content_hash`, `previous_version_id`, `superseded_at`, `coverage_start`, `coverage_end`, `language`, `labels`, `lifecycle`, `review_decision`, `reviewed_by`, `reviewed_at`, `parse_warnings`. `doc_date` becomes `published_at`.
- The `fiscal_year` filter becomes an overlap test against the coverage period; a publication date cannot answer a coverage question.
- Figures need a table of their own, keyed by `figure_id`, joined to the chunk that carries them. Nothing else reads it.
- Search defaults to the current version (`superseded_at` is null); a citation may pin a version.

## Deferred, not decided

These are deliberately not in the contract. Each is a separate piece of work with its own acceptance test.

- **The dataset resolver.** The seam exists — `values[].source = dataset` plus `dataset_citation` — but no adapter is built. The first one (FAOSTAT) is accepted only when a fetched value reproduces its figure within tolerance.
- **Vocabulary ownership.** `labels` and `entities` are versioned data, but who curates a scheme, and how a scheme version is published, is not settled.
- **Retention.** How long a superseded version stays resolvable is a policy per tenant, not a contract field.
- **Permission mapping per source system.** The contract requires `access` and forbids a default; how Drive, SharePoint, or Confluence permissions become subjects is each connector's problem.
