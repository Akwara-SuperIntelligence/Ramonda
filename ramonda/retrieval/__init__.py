"""Write chunks into retrieval.chunk and rank what the caller may see.

A chunk carries the document's security_label and access list. An access subject
is "user:<id>" or "group:<id>", in the same id space as the caller. A document
with no access row is visible to nobody.
"""

import datetime
import os
import uuid

__all__ = ["save", "search"]

MODEL = "openai/text-embedding-3-small"
WIDTH = 1536

# Tune these per deployment. The map's numbers are examples, not laws.
TOP_K = int(os.environ.get("RETRIEVAL_TOP_K", "100"))
MAX_CANDIDATES = int(os.environ.get("RETRIEVAL_MAX_CANDIDATES", "100000"))
FISCAL_YEAR_START_MONTH = int(os.environ.get("RETRIEVAL_FISCAL_START_MONTH", "1"))
if TOP_K < 1 or MAX_CANDIDATES < 1:
    raise SystemExit("RETRIEVAL_TOP_K and RETRIEVAL_MAX_CANDIDATES must be positive.")

# The filter vocabulary: chunk fields plus doc_type, department, security_label, doc_date_from, doc_date_to, fiscal_year.
_CHUNK_FILTERS = frozenset({"file_id", "parent_id", "kind"})

_DOCUMENT = """
INSERT INTO retrieval.document (org_id, file_id, security_label, doc_date, doc_type, department)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (org_id, file_id) DO UPDATE SET
    security_label = EXCLUDED.security_label,
    doc_date = EXCLUDED.doc_date,
    doc_type = EXCLUDED.doc_type,
    department = EXCLUDED.department
"""

_ACCESS = """
INSERT INTO retrieval.document_access (org_id, file_id, subject)
VALUES (%s, %s, %s)
ON CONFLICT DO NOTHING
"""

_REPLACE_ACCESS = "DELETE FROM retrieval.document_access WHERE org_id = %s AND file_id = %s"

_POLICY = (
    "c.org_id = %s",
    "d.security_label <= %s::retrieval.clearance",
    "EXISTS (SELECT 1 FROM retrieval.document_access a "
    "WHERE a.org_id = c.org_id AND a.file_id = c.file_id AND a.subject = ANY(%s))",
)

# The filter runs inside the candidate CTE, before the ranking. The guard is a safety valve, not the reducer.
_VECTOR = """
WITH q AS (SELECT %s::vector AS v),
candidates AS (
    SELECT c.id, c.file_id, c.kind, c.text, c.breadcrumb, c.embedding
    FROM retrieval.chunk c
    JOIN retrieval.document d ON d.org_id = c.org_id AND d.file_id = c.file_id
    WHERE {predicate}
    LIMIT {guard}
)
SELECT id, file_id, kind, text, breadcrumb, 1 - (embedding <=> q.v) AS score
FROM candidates, q
ORDER BY embedding <=> q.v
LIMIT %s
"""

_COLUMNS = ("id", "file_id", "kind", "text", "breadcrumb", "score")

_INSERT = """
INSERT INTO retrieval.chunk (
    id, org_id, file_id, parent_id, kind, text, breadcrumb,
    document_title, section_summary, prev_section_summary,
    excerpt_keywords, questions_this_excerpt_can_answer, embedding
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
ON CONFLICT (org_id, id) DO UPDATE SET
    file_id = EXCLUDED.file_id,
    parent_id = EXCLUDED.parent_id,
    kind = EXCLUDED.kind,
    text = EXCLUDED.text,
    breadcrumb = EXCLUDED.breadcrumb,
    document_title = EXCLUDED.document_title,
    section_summary = EXCLUDED.section_summary,
    prev_section_summary = EXCLUDED.prev_section_summary,
    excerpt_keywords = EXCLUDED.excerpt_keywords,
    questions_this_excerpt_can_answer = EXCLUDED.questions_this_excerpt_can_answer,
    embedding = EXCLUDED.embedding
"""


def _vector(values):
    if len(values) != WIDTH:
        raise ValueError(f"embedding length {len(values)}")
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row(chunk, vector, org):
    text = (chunk.get("text") or "").strip()
    kind = chunk.get("kind")
    file_id = chunk.get("file_id")
    if not text:
        raise ValueError("chunk text is empty")
    if kind not in ("text", "table"):
        raise ValueError(f"chunk kind {kind!r}")
    if not file_id:
        raise ValueError("chunk file_id is missing")
    if not org:
        raise ValueError("org is missing")
    return (
        chunk.get("id") or str(uuid.uuid4()),
        org,
        file_id,
        chunk.get("parent_id"),
        kind,
        text,
        chunk.get("breadcrumb") or "",
        chunk.get("document_title"),
        chunk.get("section_summary"),
        chunk.get("prev_section_summary"),
        chunk.get("excerpt_keywords"),
        chunk.get("questions_this_excerpt_can_answer"),
        _vector(vector),
    )


def _documents(chunks, org):
    documents = {}
    for chunk in chunks:
        file_id = chunk.get("file_id")
        if not file_id:
            raise ValueError("chunk file_id is missing")
        label = chunk.get("security_label")
        if not isinstance(label, str) or not label:
            raise ValueError(f"security_label {label!r}")
        fields = (
            label,
            tuple(sorted(str(subject) for subject in (chunk.get("access") or ()))),
            chunk.get("doc_date"),
            chunk.get("doc_type"),
            chunk.get("department"),
        )
        if file_id in documents and documents[file_id] != fields:
            raise ValueError(f"{file_id} has two labels, access lists, or document fields")
        documents[file_id] = fields
    return [(org, file_id, *fields) for file_id, fields in documents.items()]


def _record(chunk, document, org):
    _, file_id, label, access, doc_date, doc_type, department = document
    return {
        "chunk_id": chunk.get("id"),
        "org_id": org,
        "file_id": file_id,
        "parent_id": chunk.get("parent_id"),
        "kind": chunk.get("kind"),
        "text": (chunk.get("text") or "").strip(),
        "breadcrumb": chunk.get("breadcrumb") or "",
        "document_title": chunk.get("document_title"),
        "excerpt_keywords": chunk.get("excerpt_keywords"),
        "questions": chunk.get("questions_this_excerpt_can_answer"),
        "security_label": label,
        "access": list(access),
        "doc_date": _iso(doc_date),
        "doc_type": doc_type,
        "department": department,
    }


def _subjects(caller):
    return [f"user:{caller.user}", *(f"group:{group}" for group in caller.groups)]


def _fiscal_range(year):
    year = int(year)
    return (
        datetime.date(year, FISCAL_YEAR_START_MONTH, 1),
        datetime.date(year + 1, FISCAL_YEAR_START_MONTH, 1),
    )


def _embed(texts):
    from openai import OpenAI

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is missing.")
    client = OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1")
    response = client.embeddings.create(model=MODEL, input=texts)
    ordered = [None] * len(texts)
    for item in response.data:
        ordered[item.index] = item.embedding
    return ordered


def _connect():
    import psycopg

    password = os.environ.get("RETRIEVAL_DB_PASSWORD")
    if not password:
        raise SystemExit("RETRIEVAL_DB_PASSWORD is missing.")
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        dbname=os.environ.get("POSTGRES_DB", "ramonda"),
        user="retrieval",
        password=password,
    )


def _predicate(caller, filters):
    # The organisation, the label, and the access list are mandatory. A filter cannot replace them.
    clauses = list(_POLICY)
    params = [caller.org, caller.clearance, _subjects(caller)]
    for key, value in (filters or {}).items():
        if key in _CHUNK_FILTERS:
            clauses.append(f"c.{key} = %s")
            params.append(value)
        elif key in ("doc_type", "department"):
            if isinstance(value, (list, tuple, set)):
                clauses.append(f"d.{key} = ANY(%s)")
                params.append(list(value))
            else:
                clauses.append(f"d.{key} = %s")
                params.append(value)
        elif key == "security_label":
            labels = [value] if isinstance(value, str) else list(value)
            clauses.append("d.security_label::text = ANY(%s)")
            params.append(labels)
        elif key == "doc_date_from":
            clauses.append("d.doc_date >= %s")
            params.append(value)
        elif key == "doc_date_to":
            clauses.append("d.doc_date <= %s")
            params.append(value)
        elif key == "fiscal_year":
            start, end = _fiscal_range(value)
            clauses.append("d.doc_date >= %s AND d.doc_date < %s")
            params.extend([start, end])
        else:
            raise ValueError(f"unknown filter {key!r}")
    return " AND ".join(clauses), params


def _os_filter(caller, filters):
    # The second builder for the same filter vocabulary. Change both builders together.
    clauses = [
        {"term": {"org_id": caller.org}},
        {"terms": {"security_label": list(caller.labels)}},
        {"terms": {"access": _subjects(caller)}},
    ]
    for key, value in (filters or {}).items():
        if key in _CHUNK_FILTERS:
            clauses.append({"term": {key: value}})
        elif key in ("doc_type", "department", "security_label"):
            clauses.append({"terms": {key: [value] if isinstance(value, str) else list(value)}})
        elif key in ("doc_date_from", "doc_date_to"):
            side = "gte" if key.endswith("from") else "lte"
            clauses.append({"range": {"doc_date": {side: _iso(value)}}})
        elif key == "fiscal_year":
            start, end = _fiscal_range(value)
            clauses.append({"range": {"doc_date": {"gte": start.isoformat(), "lt": end.isoformat()}}})
        else:
            raise ValueError(f"unknown filter {key!r}")
    return clauses


def _rank(sql, params):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(zip(_COLUMNS, row)) for row in cur.fetchall()]


def _fuse(lists, limit):
    # Reciprocal rank fusion: no score calibration, 60 is the usual constant.
    scores = {}
    rows = {}
    for ranked in lists:
        for rank, row in enumerate(ranked, 1):
            key = row["id"]
            rows[key] = row
            scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank)
    order = sorted(scores, key=lambda key: (-scores[key], key))
    return [{**rows[key], "score": round(scores[key], 6)} for key in order[:limit]]


def search(query, caller, filters=None):
    query = (query or "").strip()
    if not query:
        return []
    predicate, params = _predicate(caller, filters)
    from . import opensearch

    vector = _vector(_embed([query])[0])
    ranked = [
        _rank(
            _VECTOR.format(predicate=predicate, guard=MAX_CANDIDATES),
            [vector, *params, TOP_K],
        ),
        opensearch.search(query, _os_filter(caller, filters), TOP_K),
    ]
    return _fuse(ranked, TOP_K)


def save(caller, chunks):
    if not chunks:
        return
    for chunk in chunks:
        if not chunk.get("id"):
            chunk["id"] = str(uuid.uuid4())
    documents = _documents(chunks, caller.org)
    texts = [chunk.get("text") or "" for chunk in chunks]
    rows = [_row(chunk, vector, caller.org) for chunk, vector in zip(chunks, _embed(texts))]
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                _DOCUMENT,
                [
                    (org, file_id, label, doc_date, doc_type, department)
                    for org, file_id, label, _, doc_date, doc_type, department in documents
                ],
            )
            for org, file_id, _, access, _, _, _ in documents:
                cur.execute(_REPLACE_ACCESS, (org, file_id))
                cur.executemany(_ACCESS, [(org, file_id, subject) for subject in access])
            cur.executemany(_INSERT, rows)
        conn.commit()
    # The rows are the source. A failed index fails the run; the next save repairs it.
    from . import opensearch

    by_file = {row[1]: row for row in documents}
    opensearch.index([_record(chunk, by_file[chunk["file_id"]], caller.org) for chunk in chunks])


def _self_check():
    from types import SimpleNamespace

    caller = SimpleNamespace(
        user="hassan",
        org="akwara",
        groups=("finance",),
        clearance="confidential",
        labels=("public", "internal", "confidential"),
    )
    assert _subjects(caller) == ["user:hassan", "group:finance"]
    start, end = _fiscal_range(2025)
    assert start.month == FISCAL_YEAR_START_MONTH and start.year == 2025
    assert end == datetime.date(2026, FISCAL_YEAR_START_MONTH, 1)
    assert "LIMIT 7" in _VECTOR.format(predicate="1 = 1", guard=7)
    zeros = [0.0] * WIDTH
    row = _row(
        {
            "file_id": "deck",
            "kind": "table",
            "text": " hello ",
            "breadcrumb": "Intro",
            "document_title": "A title",
        },
        zeros,
        caller.org,
    )
    assert row[1] == "akwara"
    assert row[2] == "deck"
    assert row[3] is None
    assert row[4] == "table"
    assert row[5] == "hello"
    assert row[7] == "A title"
    assert row[12] == "[" + ",".join(["0.0"] * WIDTH) + "]"
    assert _INSERT.count("%s") == len(row)
    assert _DOCUMENT.count("%s") == 6
    assert _ACCESS.count("%s") == 3
    assert _REPLACE_ACCESS.count("%s") == 2
    kept = _row(
        {"id": "a", "file_id": "f", "kind": "text", "text": "x", "parent_id": "p"},
        zeros,
        caller.org,
    )
    assert kept[0] == "a" and kept[3] == "p"
    for bad in ({"kind": "text", "text": "x"}, {"file_id": "f", "kind": "text"}):
        try:
            _row(bad, zeros, caller.org)
        except ValueError:
            continue
        raise AssertionError(f"row was accepted: {bad}")

    same = [
        {"file_id": "f", "security_label": "internal", "access": ["user:a"]},
        {"file_id": "f", "security_label": "internal", "access": ["user:a"]},
    ]
    assert _documents(same, caller.org) == [
        ("akwara", "f", "internal", ("user:a",), None, None, None)
    ]
    assert _documents([{"file_id": "g", "security_label": "public"}], caller.org) == [
        ("akwara", "g", "public", (), None, None, None)
    ]
    assert _documents(
        [{"file_id": "h", "security_label": "public", "access": ["group:g", "user:a"]}],
        caller.org,
    ) == [("akwara", "h", "public", ("group:g", "user:a"), None, None, None)]
    try:
        _documents([same[0], {**same[1], "security_label": "public"}], caller.org)
    except ValueError:
        pass
    else:
        raise AssertionError("two labels for one file were accepted")
    for bad in ({"file_id": "f"}, {"security_label": "public"}):
        try:
            _documents([bad], caller.org)
        except ValueError:
            continue
        raise AssertionError(f"document was accepted: {bad}")

    predicate, params = _predicate(caller, {})
    assert predicate == (
        "c.org_id = %s AND d.security_label <= %s::retrieval.clearance "
        "AND EXISTS (SELECT 1 FROM retrieval.document_access a "
        "WHERE a.org_id = c.org_id AND a.file_id = c.file_id AND a.subject = ANY(%s))"
    )
    assert params == ["akwara", "confidential", ["user:hassan", "group:finance"]]
    predicate, params = _predicate(caller, {"file_id": "deck", "doc_type": ["contract"]})
    assert predicate.endswith(" AND c.file_id = %s AND d.doc_type = ANY(%s)")
    assert params == [
        "akwara",
        "confidential",
        ["user:hassan", "group:finance"],
        "deck",
        ["contract"],
    ]
    os_filter = _os_filter(caller, {"doc_type": "contract", "fiscal_year": 2025})
    assert {"term": {"org_id": "akwara"}} in os_filter
    assert {"terms": {"security_label": ["public", "internal", "confidential"]}} in os_filter
    assert {"terms": {"doc_type": ["contract"]}} in os_filter
    try:
        _predicate(caller, {"org_id": "othercorp"})
    except ValueError:
        pass
    else:
        raise AssertionError("a filter could change the caller's org")

    left = [{"id": "a"}, {"id": "b"}]
    right = [{"id": "b"}, {"id": "c"}]
    fused = _fuse([left, right], 3)
    assert [row["id"] for row in fused] == ["b", "a", "c"]
    assert fused[0]["score"] > fused[1]["score"]
    assert _fuse([[{"id": "a"}]], 0) == []
    assert search("", caller) == []


if __name__ == "__main__":
    _self_check()
