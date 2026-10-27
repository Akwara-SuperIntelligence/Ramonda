"""The ingestion contract: the fields, the vocabularies, and the checks.

docs/ingestion-contract.md beside this module is the normative text. This module is
the checkable copy. Its self-check fails when the field tables in the document and
the lists here disagree, and it runs with `python -m ramonda.ingestion.contract`.
"""

import hashlib
from pathlib import Path

DOC = Path(__file__).resolve().parent / "docs" / "ingestion-contract.md"

DOCUMENT = (
    "org_id",
    "file_id",
    "version_id",
    "content_hash",
    "previous_version_id",
    "superseded_at",
    "source_system",
    "source_id",
    "source_url",
    "mime_type",
    "title",
    "title_source",
    "published_at",
    "coverage_start",
    "coverage_end",
    "language",
    "labels",
    "lifecycle",
    "quarantine_reason",
    "review_decision",
    "reviewed_by",
    "reviewed_at",
    "security_label",
    "access",
    "department",
    "parser",
    "parser_version",
    "parser_strategy",
    "parse_warnings",
)

CHUNK = (
    "id",
    "org_id",
    "file_id",
    "version_id",
    "kind",
    "text",
    "breadcrumb",
    "anchor_paragraph_start",
    "anchor_paragraph_count",
    "anchor_row_start",
    "anchor_row_count",
    "anchor_page",
    "anchor_quote",
    "derived_from",
    "figure_ref",
    "parser",
    "security_label",
    "access",
    "document_title",
    "section_summary",
    "prev_section_summary",
    "excerpt_keywords",
    "questions",
    "entities",
    "enriched_with",
)

FIGURE = (
    "figure_id",
    "org_id",
    "file_id",
    "version_id",
    "chunk_id",
    "figure_label",
    "caption",
    "image_ref",
    "anchor_page",
    "bbox",
    "chart_type",
    "axis_labels",
    "series",
    "values",
    "dataset_citation",
    "extractor",
    "review_decision",
)

TERM = ("scheme", "term_id", "label", "confidence", "source", "evidence")

REQUIRED_DOCUMENT = (
    "org_id",
    "file_id",
    "version_id",
    "content_hash",
    "source_system",
    "source_id",
    "mime_type",
    "lifecycle",
    "security_label",
    "access",
)
REQUIRED_CHUNK = (
    "id",
    "org_id",
    "file_id",
    "version_id",
    "kind",
    "text",
    "breadcrumb",
    "anchor_quote",
    "derived_from",
    "security_label",
    "access",
)
REQUIRED_FIGURE = ("figure_id", "org_id", "file_id", "version_id", "chunk_id")

ENRICHED = (
    "section_summary",
    "prev_section_summary",
    "excerpt_keywords",
    "questions",
    "entities",
)

KIND = ("text", "table")
DERIVED_FROM = ("body", "table", "figure", "caption")
LIFECYCLE = (
    "discovered",
    "fetched",
    "parsed",
    "chunked",
    "enriched",
    "indexed",
    "quarantined",
)
REVIEW = ("approved", "rejected")
VALUE_SOURCE = ("label_ocr", "vlm_estimate", "dataset")
SECURITY = ("public", "internal", "confidential", "restricted")
TERM_SOURCE = ("folder", "filename", "embedded-metadata", "model", "human")
TITLE_SOURCE = ("embedded-metadata", "filename", "model")


def chunk_id(file_id, version_id, anchor, text):
    # I10: unchanged content keeps its id; any change to the four parts makes a new one.
    parts = [file_id, version_id]
    for key in ("paragraph_start", "paragraph_count", "row_start", "row_count", "page"):
        parts.append(str(anchor.get(key, "")))
    parts.append(text)
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]


def figure_id(file_id, version_id, anchor):
    return hashlib.sha256(
        "\0".join([file_id, version_id, str(anchor)]).encode("utf-8")
    ).hexdigest()[:32]


def embed_form(chunk):
    # I1: the breadcrumb is context, and only the embedded form carries it.
    crumb = chunk.get("breadcrumb") or ""
    return f"{crumb}\n\n{chunk['text']}".strip()


def may_assert(value):
    # I7: only a value that came from a dataset may be stated as fact.
    return value.get("source") == "dataset"


def _missing(record, required):
    return [key for key in required if key not in record or record[key] is None]


def _terms(terms, where):
    if not isinstance(terms, (list, tuple)):
        raise ValueError(f"{where} must be a list")
    for term in terms:
        for key in ("scheme", "term_id", "source"):
            if not term.get(key):
                raise ValueError(f"{where} term is missing {key}: {term!r}")
        if term["source"] not in TERM_SOURCE:
            raise ValueError(f"{where} term source {term['source']!r}")


def _subjects(subjects):
    if not isinstance(subjects, (list, tuple)):
        raise ValueError("access must be a list")
    for subject in subjects:
        if not isinstance(subject, str) or not subject.startswith(("user:", "group:")):
            raise ValueError(f"access subject {subject!r}")


def validate_document(record):
    missing = _missing(record, REQUIRED_DOCUMENT)
    if missing:
        raise ValueError(f"document is missing {missing}")
    if record["lifecycle"] not in LIFECYCLE:
        raise ValueError(f"lifecycle {record['lifecycle']!r}")
    if record["security_label"] not in SECURITY:
        raise ValueError(f"security_label {record['security_label']!r}")
    _subjects(record["access"])
    if record["lifecycle"] == "quarantined" and not record.get("quarantine_reason"):
        raise ValueError("a quarantined document needs a reason")
    if record.get("title") and record.get("title_source") not in TITLE_SOURCE:
        raise ValueError(f"title_source {record.get('title_source')!r}")
    if record.get("review_decision"):
        if record["review_decision"] not in REVIEW:
            raise ValueError(f"review_decision {record['review_decision']!r}")
        if not record.get("reviewed_by") or not record.get("reviewed_at"):
            raise ValueError("a review needs a reviewer and a time")
    _terms(record.get("labels") or [], "labels")
    return record


def validate_chunk(record, document=None):
    missing = _missing(record, REQUIRED_CHUNK)
    if missing:
        raise ValueError(f"chunk is missing {missing}")
    if record["kind"] not in KIND:
        raise ValueError(f"kind {record['kind']!r}")
    text = record["text"]
    if not text.strip():
        raise ValueError("chunk text is empty")
    crumb = record["breadcrumb"] or ""
    if crumb and crumb in text:
        raise ValueError("chunk text contains its breadcrumb")
    if record["derived_from"] not in DERIVED_FROM:
        raise ValueError(f"derived_from {record['derived_from']!r}")
    if record["derived_from"] in ("figure", "caption") and not record.get("figure_ref"):
        raise ValueError("figure-derived text needs a figure_ref")
    quote = record["anchor_quote"]
    if not quote or quote not in text:
        raise ValueError("anchor_quote must be a non-empty part of the text")
    page = record.get("anchor_page")
    if page is not None and (type(page) is not int or page < 1):
        raise ValueError(f"anchor_page {page!r} is not a printed page number")
    if record["kind"] == "text" and record.get("anchor_paragraph_start") is None:
        raise ValueError("a text chunk needs a paragraph anchor")
    if record["kind"] == "table" and record.get("anchor_row_start") is None:
        raise ValueError("a table chunk needs a row anchor")
    if any(record.get(key) for key in ENRICHED) and not record.get("enriched_with"):
        raise ValueError("enriched fields need enriched_with")
    _subjects(record["access"])
    _terms(record.get("entities") or [], "entities")
    if document is not None:
        _same(record, document, "file_id")
        _same(record, document, "version_id")
        _same(record, document, "security_label")
        if sorted(record["access"]) != sorted(document["access"]):
            raise ValueError("chunk access must equal the document's")
        if record.get("document_title") and document.get("title"):
            if record["document_title"] != document["title"]:
                raise ValueError("chunk document_title is not the document's title")
    return record


def validate_figure(record, document=None):
    missing = _missing(record, REQUIRED_FIGURE)
    if missing:
        raise ValueError(f"figure is missing {missing}")
    values = record.get("values") or []
    for value in values:
        if value.get("source") not in VALUE_SOURCE:
            raise ValueError(f"value source {value.get('source')!r}")
        if value["source"] == "dataset" and not record.get("dataset_citation"):
            raise ValueError("a dataset value needs a dataset_citation")
    if record.get("dataset_citation"):
        for key in ("dataset", "accessed"):
            if not record["dataset_citation"].get(key):
                raise ValueError(f"dataset_citation is missing {key}")
    if any(record.get(key) for key in ("chart_type", "axis_labels", "series", "values")):
        if not record.get("extractor"):
            raise ValueError("figure extraction needs its extractor")
    if document is not None:
        _same(record, document, "file_id")
        _same(record, document, "version_id")
    return record


def _same(record, document, key, record_key=None):
    record_key = record_key or key
    if record.get(record_key) != document.get(key):
        raise ValueError(f"{record_key} {record.get(record_key)!r} is not the document's {key!r}")


def documented_fields(path=DOC):
    names = set()
    inside = False
    for line in path.read_text().splitlines():
        if line.strip() == "| Field | Type | Required | Class | Notes |":
            inside = True
            continue
        if not inside:
            continue
        if not line.startswith("|"):
            inside = False
            continue
        cell = line.split("|")[1].strip().strip("`").strip()
        if cell and set(cell) != {"-"}:
            names.add(cell)
    return names


def _self_check():
    document = {
        "org_id": "akwara",
        "file_id": "drive:x",
        "version_id": "v1",
        "content_hash": "abc",
        "source_system": "drive",
        "source_id": "x",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "lifecycle": "chunked",
        "security_label": "internal",
        "access": ["group:food"],
        "title": "Africa Coordinated Positions",
        "title_source": "embedded-metadata",
        "labels": [
            {"scheme": "codex@1", "term_id": "session-report", "source": "model", "confidence": 0.8}
        ],
    }
    assert validate_document(document) is document
    for bad in (
        {},
        {**document, "lifecycle": "published"},
        {**document, "security_label": "secret"},
        {**document, "access": ["akwara"]},
        {**document, "title": "T", "title_source": "guess"},
        {**document, "lifecycle": "quarantined"},
        {**document, "review_decision": "approved"},
        {**document, "labels": [{"scheme": "s", "term_id": "t", "source": "vibes"}]},
    ):
        try:
            validate_document(bad)
        except ValueError:
            continue
        raise AssertionError(f"document was accepted: {bad}")

    anchor = {"paragraph_start": 0, "paragraph_count": 1}
    chunk = {
        "id": chunk_id("drive:x", "v1", anchor, "Africa grows the cashews."),
        "org_id": "akwara",
        "file_id": "drive:x",
        "version_id": "v1",
        "kind": "text",
        "text": "Africa grows the cashews.",
        "breadcrumb": "CAC49 > Cashews",
        "anchor_paragraph_start": 0,
        "anchor_paragraph_count": 1,
        "anchor_quote": "Africa grows the cashews.",
        "derived_from": "body",
        "security_label": "internal",
        "access": ["group:food"],
        "document_title": "Africa Coordinated Positions",
    }
    assert validate_chunk(chunk, document) is chunk
    assert embed_form(chunk) == "CAC49 > Cashews\n\nAfrica grows the cashews."
    assert chunk_id("drive:x", "v1", anchor, "Africa grows the cashews.") == chunk["id"]
    assert chunk_id("drive:x", "v1", anchor, "Africa grows the cashews!") != chunk["id"]
    for bad in (
        {**chunk, "text": "CAC49 > Cashews Africa grows the cashews."},
        {**chunk, "anchor_quote": "not in the text"},
        {**chunk, "kind": "figure"},
        {**chunk, "derived_from": "figure"},
        {**chunk, "anchor_page": 0},
        {**chunk, "security_label": "public"},
        {**chunk, "access": ["group:other"]},
        {**chunk, "section_summary": "Says cashews grow."},
        {**chunk, "anchor_paragraph_start": None},
    ):
        try:
            validate_chunk(bad, document)
        except ValueError:
            continue
        raise AssertionError(f"chunk was accepted: {bad}")
    table = {**chunk, "kind": "table", "text": "<table><tr><td>6</td></tr></table>", "anchor_quote": "<table>"}
    table.update({"anchor_row_start": 0, "anchor_row_count": 1, "anchor_paragraph_start": None})
    assert validate_chunk(table, document) is table
    assert not may_assert({"source": "vlm_estimate"}) and may_assert({"source": "dataset"})

    figure = {
        "figure_id": figure_id("drive:x", "v1", "img3"),
        "org_id": "akwara",
        "file_id": "drive:x",
        "version_id": "v1",
        "chunk_id": chunk["id"],
        "caption": "Top cashew-producing countries, 2023",
    }
    assert validate_figure(figure, document) is figure
    for bad in (
        {**figure, "values": [{"value": 36, "source": "guess"}]},
        {**figure, "values": [{"value": 36, "source": "dataset"}]},
        {**figure, "chart_type": "bar"},
        {
            **figure,
            "values": [{"value": 36, "source": "dataset"}],
            "dataset_citation": {"dataset": "FAOSTAT"},
            "extractor": {"name": "x", "version": "1"},
        },
    ):
        try:
            validate_figure(bad, document)
        except ValueError:
            continue
        raise AssertionError(f"figure was accepted: {bad}")
    cited = {
        **figure,
        "values": [{"value": 36, "source": "dataset"}],
        "dataset_citation": {"dataset": "FAOSTAT", "accessed": "2026-10-01"},
        "extractor": {"name": "faostat", "version": "1"},
    }
    assert validate_figure(cited, document) is cited

    expected = set(DOCUMENT + CHUNK + FIGURE + TERM)
    found = documented_fields()
    if found != expected:
        raise AssertionError(
            f"the contract document and this module disagree: only in code {sorted(expected - found)}, "
            f"only in the document {sorted(found - expected)}"
        )


if __name__ == "__main__":
    _self_check()
    print("contract self-check passed", flush=True)
