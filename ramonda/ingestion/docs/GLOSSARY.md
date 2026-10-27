# Ingestion

The path a source file takes from a connector to a retrievable chunk: intake, parse, chunk, enrich, and the picture text that comes with it. This glossary fixes the words the ingestion contract uses. It describes concepts, not implementation.

## Stages

**Intake**:
Accepting a file from a source system together with the fields that system already knows, before anything is parsed.
_Avoid_: ingest, fetch, import, load

**Parse**:
Turning a file's bytes into the block model. A format is supported when some parse adapter claims it; nothing else decides.
_Avoid_: extract, convert, read

**Enrichment**:
Adding derived fields to chunks by calling a model. It can be re-run, partly done, or absent, and the pipeline must still work.
_Avoid_: augmentation, tagging, annotation

## Structure

**Document**:
The unit that carries identity, version, provenance, and access. One document becomes many chunks.
_Avoid_: file, record, asset, item, source

**Block**:
One structural unit of a parsed document: a heading, paragraph, list item, table, or figure. Parse adapters produce blocks; chunks are made from blocks.
_Avoid_: element, node, segment

**Block model**:
The single normalised shape every parse adapter must produce, so that chunking never depends on which format was parsed.
_Avoid_: document model, AST, schema

**Chunk**:
A retrievable piece of a document with exactly one citation anchor. Chunks are what retrieval ranks and what the agent reads.
_Avoid_: node, passage, fragment, excerpt, leaf

**Section**:
The heading path a chunk sits under, taken from the document root.
_Avoid_: heading, parent, hierarchy

**Breadcrumb**:
A section rendered as text, root first, joined by " > ".
_Avoid_: path, trail, hierarchy string

**Anchor**:
The position that identifies where a chunk sits in its document: section plus paragraph range, and a page only where the source has real pages. It travels with a short frozen quote, so an anchor whose text has moved is detectable.
_Avoid_: location, locator, offset, span, coordinates

**Figure**:
A picture in a document together with the caption that names it, treated as one unit.
_Avoid_: image, chart, graphic, visual

**Figure record**:
The claims attached to a figure: its values, where each value came from, and the extractor that read it.
_Avoid_: image metadata, chart data, alt text

**Picture text**:
Text recovered from a picture rather than from the document's text layer. It is evidence about the picture, not the document's own prose.
_Avoid_: OCR text, image text, alt text

## Identity and trust

**Document version**:
One immutable state of a document's content, identified by its content hash. A citation names the version it was made against.
_Avoid_: revision, snapshot, copy

**Superseded version**:
A document version that a newer one replaced, kept so that citations made against it still resolve.
_Avoid_: old version, stale version, deleted version

**Content hash**:
The digest of a document's bytes. It detects change and deduplicates; it is not an identity.
_Avoid_: checksum, fingerprint, id

**Parse adapter**:
A component that turns one family of byte formats into the block model and declares the capabilities it needs and the capabilities it produces.
_Avoid_: parser, extractor, reader, loader

**Quarantine**:
The state of a document the pipeline accepted but could not parse, or whose access it could not map. It keeps its failure reason, and is never dropped or silently skipped.
_Avoid_: skip, error, reject, dead letter

**Source field**:
A field read from a document's bytes or its source system: identity, version, dates, coverage, access.
_Avoid_: metadata, intrinsic field, system field

**Derived field**:
A field computed from a document's content rather than read from the source. It may be absent, it records the model and prompt that produced it, and it is never authoritative.
_Avoid_: enrichment, annotation, metadata, feature

**Term**:
A value drawn from a controlled vocabulary, identified by its scheme and term id rather than by its label.
_Avoid_: tag, keyword, label, category

**Asserted number**:
A number the pipeline is willing to have stated as fact. It requires a named dataset as its source; a number read from a figure's pixels is not one.
_Avoid_: extracted value, reading, data point, chart value

**Lifecycle**:
The pipeline's own state for a document, from discovery to indexed or quarantined. It is never a person's judgement.
_Avoid_: status, state, approval state

**Review decision**:
A person's signed judgement that a document may be used. It gates use, never intake.
_Avoid_: approval, status, sign-off
