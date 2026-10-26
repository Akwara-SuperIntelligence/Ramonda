"""Write chunks into retrieval.chunk. The vector is a column on that row."""

import os
import uuid

__all__ = ["save"]

# shortcut: 1536 is text-embedding-3-small, same width as the column
MODEL = "openai/text-embedding-3-small"
WIDTH = 1536

_INSERT = """
INSERT INTO retrieval.chunk (
    id, file_id, parent_id, kind, text, breadcrumb,
    document_title, section_summary, prev_section_summary,
    excerpt_keywords, questions_this_excerpt_can_answer, embedding
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
ON CONFLICT (id) DO UPDATE SET
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


def _row(chunk, vector):
    text = (chunk.get("text") or "").strip()
    kind = chunk.get("kind")
    file_id = chunk.get("file_id")
    if not text:
        raise ValueError("chunk text is empty")
    if kind not in ("text", "table"):
        raise ValueError(f"chunk kind {kind!r}")
    if not file_id:
        raise ValueError("chunk file_id is missing")
    return (
        chunk.get("id") or str(uuid.uuid4()),
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


def save(chunks):
    if not chunks:
        return
    texts = [chunk.get("text") or "" for chunk in chunks]
    rows = [_row(chunk, vector) for chunk, vector in zip(chunks, _embed(texts))]
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(_INSERT, rows)
        conn.commit()


def _self_check():
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
    )
    assert row[1] == "deck"
    assert row[2] is None
    assert row[3] == "table"
    assert row[4] == "hello"
    assert row[6] == "A title"
    assert row[11] == "[" + ",".join(["0.0"] * WIDTH) + "]"
    kept = _row({"id": "a", "file_id": "f", "kind": "text", "text": "x", "parent_id": "p"}, zeros)
    assert kept[0] == "a" and kept[2] == "p"
    try:
        _row({"kind": "text", "text": "x"}, zeros)
    except ValueError:
        return
    raise AssertionError("missing file_id was accepted")
