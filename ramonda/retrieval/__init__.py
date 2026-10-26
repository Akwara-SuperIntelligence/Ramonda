"""Write chunks into retrieval.chunk and read back the ids the caller may see.

A chunk carries the document's security_label and access list. An access subject
is "user:<id>" or "group:<id>", in the same id space as the caller. A document
with no access row is visible to nobody.
"""

import os
import uuid

__all__ = ["matching_ids", "save"]

# shortcut: equality on chunk columns only; Fortune 500 adds typed document fields (date, department, type) as filter names.
_FILTERS = frozenset({
    "file_id",
    "parent_id",
    "kind",
    "text",
    "breadcrumb",
    "document_title",
    "section_summary",
    "prev_section_summary",
    "excerpt_keywords",
    "questions_this_excerpt_can_answer",
})

# shortcut: 1536 is text-embedding-3-small, same width as the column
MODEL = "openai/text-embedding-3-small"
WIDTH = 1536

_DOCUMENT = """
INSERT INTO retrieval.document (org_id, file_id, security_label)
VALUES (%s, %s, %s)
ON CONFLICT (org_id, file_id) DO UPDATE SET security_label = EXCLUDED.security_label
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

_SELECT = (
    "SELECT c.id FROM retrieval.chunk c "
    "JOIN retrieval.document d ON d.org_id = c.org_id AND d.file_id = c.file_id "
    "WHERE "
)

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
        access = tuple(sorted(str(subject) for subject in (chunk.get("access") or ())))
        if file_id in documents and documents[file_id] != (label, access):
            raise ValueError(f"{file_id} has two labels or access lists")
        documents[file_id] = (label, access)
    return [(org, file_id, label, access) for file_id, (label, access) in documents.items()]


def _subjects(caller):
    return [f"user:{caller.user}", *(f"group:{group}" for group in caller.groups)]


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


def _where(caller, filters):
    # The organisation, the label, and the access list are mandatory. A filter cannot replace them.
    clauses = list(_POLICY)
    params = [caller.org, caller.clearance, _subjects(caller)]
    for key, value in (filters or {}).items():
        if key not in _FILTERS:
            raise ValueError(f"unknown filter {key!r}")
        if value is None:
            clauses.append(f"c.{key} IS NULL")
        else:
            clauses.append(f"c.{key} = %s")
            params.append(value)
    return _SELECT + " AND ".join(clauses), params


def matching_ids(caller, filters=None):
    sql, params = _where(caller, filters or {})
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [row[0] for row in cur.fetchall()]


def save(caller, chunks):
    if not chunks:
        return
    documents = _documents(chunks, caller.org)
    texts = [chunk.get("text") or "" for chunk in chunks]
    rows = [_row(chunk, vector, caller.org) for chunk, vector in zip(chunks, _embed(texts))]
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(_DOCUMENT, [(org, file_id, label) for org, file_id, label, _ in documents])
            for org, file_id, _, access in documents:
                cur.execute(_REPLACE_ACCESS, (org, file_id))
                cur.executemany(_ACCESS, [(org, file_id, subject) for subject in access])
            cur.executemany(_INSERT, rows)
        conn.commit()


def _self_check():
    from types import SimpleNamespace

    caller = SimpleNamespace(
        user="hassan", org="akwara", groups=("finance",), clearance="confidential"
    )
    assert _subjects(caller) == ["user:hassan", "group:finance"]
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
    assert _DOCUMENT.count("%s") == 3
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
    assert _documents(same, caller.org) == [("akwara", "f", "internal", ("user:a",))]
    assert _documents([{"file_id": "g", "security_label": "public"}], caller.org) == [
        ("akwara", "g", "public", ())
    ]
    assert _documents(
        [{"file_id": "h", "security_label": "public", "access": ["group:g", "user:a"]}],
        caller.org,
    ) == [("akwara", "h", "public", ("group:g", "user:a"))]
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

    sql, params = _where(caller, {})
    assert sql == (
        "SELECT c.id FROM retrieval.chunk c "
        "JOIN retrieval.document d ON d.org_id = c.org_id AND d.file_id = c.file_id "
        "WHERE c.org_id = %s AND d.security_label <= %s::retrieval.clearance "
        "AND EXISTS (SELECT 1 FROM retrieval.document_access a "
        "WHERE a.org_id = c.org_id AND a.file_id = c.file_id AND a.subject = ANY(%s))"
    )
    assert params == ["akwara", "confidential", ["user:hassan", "group:finance"]]
    sql, params = _where(caller, {"file_id": "deck", "document_title": None})
    assert sql.endswith(" AND c.file_id = %s AND c.document_title IS NULL")
    assert params == ["akwara", "confidential", ["user:hassan", "group:finance"], "deck"]
    try:
        _where(caller, {"org_id": "othercorp"})
    except ValueError:
        pass
    else:
        raise AssertionError("a filter could change the caller's org")


if __name__ == "__main__":
    _self_check()
