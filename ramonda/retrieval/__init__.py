"""Write chunks into retrieval.chunk and read back the ids the caller may see."""

import os
import uuid

__all__ = ["matching_ids", "save"]

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
    # The caller's organisation is the only mandatory clause. A filter cannot replace it.
    clauses = ["org_id = %s"]
    params = [caller.org]
    for key, value in (filters or {}).items():
        if key not in _FILTERS:
            raise ValueError(f"unknown filter {key!r}")
        if value is None:
            clauses.append(f"{key} IS NULL")
        else:
            clauses.append(f"{key} = %s")
            params.append(value)
    return "SELECT id FROM retrieval.chunk WHERE " + " AND ".join(clauses), params


def matching_ids(caller, filters=None):
    sql, params = _where(caller, filters or {})
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [row[0] for row in cur.fetchall()]


def save(caller, chunks):
    if not chunks:
        return
    texts = [chunk.get("text") or "" for chunk in chunks]
    rows = [_row(chunk, vector, caller.org) for chunk, vector in zip(chunks, _embed(texts))]
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(_INSERT, rows)
        conn.commit()


def _self_check():
    from types import SimpleNamespace

    caller = SimpleNamespace(org="akwara")
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
    sql, params = _where(caller, {})
    assert sql == "SELECT id FROM retrieval.chunk WHERE org_id = %s"
    assert params == ["akwara"]
    sql, params = _where(caller, {"file_id": "deck", "document_title": None})
    assert sql == (
        "SELECT id FROM retrieval.chunk "
        "WHERE org_id = %s AND file_id = %s AND document_title IS NULL"
    )
    assert params == ["akwara", "deck"]
    try:
        _where(caller, {"org_id": "othercorp"})
    except ValueError:
        pass
    else:
        raise AssertionError("a filter could change the caller's org")


if __name__ == "__main__":
    _self_check()
