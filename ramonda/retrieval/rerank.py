"""Re-rank the fused pool with a local cross-encoder."""

import os
import threading

# shortcut: a small English model; set RETRIEVAL_RERANK_MODEL for another, and pre-download it for an offline host.
MODEL = os.environ.get("RETRIEVAL_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
BATCH = int(os.environ.get("RETRIEVAL_RERANK_BATCH", "16"))
if BATCH < 1:
    raise SystemExit("RETRIEVAL_RERANK_BATCH must be positive.")
# shortcut: a character budget stands in for the tokenizer; the model still truncates at its own limit.
MAX_CHARS = int(os.environ.get("RETRIEVAL_RERANK_MAX_CHARS", "1800"))
if MAX_CHARS < 1:
    raise SystemExit("RETRIEVAL_RERANK_MAX_CHARS must be positive.")

_lock = threading.Lock()
_model = None


def _predict(pairs):
    from sentence_transformers import CrossEncoder
    from torch import nn

    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = CrossEncoder(MODEL, activation_fn=nn.Sigmoid())
    return _model.predict(pairs, batch_size=BATCH)


def _document(row):
    # The body comes first so the token limit cannot push it out; the enriched fields follow.
    meta = "\n".join(
        part
        for part in (
            row.get("document_title"),
            row.get("breadcrumb"),
            row.get("excerpt_keywords"),
            row.get("questions"),
        )
        if part
    )
    return f"{row.get('text') or ''}\n{meta}".strip()[:MAX_CHARS]


def rank(query, rows):
    if not rows:
        return []
    pairs = [(query, _document(row)) for row in rows]
    scores = _predict(pairs)
    ranked = [{**row, "score": float(score)} for row, score in zip(rows, scores)]
    return sorted(ranked, key=lambda row: -row["score"])


def _self_check():
    global _predict
    original = _predict
    seen = []

    def fake(pairs):
        seen.extend(pairs)
        return [0.2, 0.9] if len(pairs) == 2 else [0.5 for _ in pairs]

    _predict = fake
    try:
        rows = [
            {
                "id": "a",
                "document_title": "T",
                "breadcrumb": "B",
                "excerpt_keywords": "K",
                "questions": "Q",
                "text": "X",
            },
            {"id": "c", "text": "Y"},
        ]
        ranked = rank("q", rows)
        assert [row["id"] for row in ranked] == ["c", "a"]
        assert ranked[0]["score"] == 0.9
        assert seen[0] == ("q", "X\nT\nB\nK\nQ")
        assert rank("q", []) == []
        long_row = {"id": "z", "text": "x" * (MAX_CHARS + 100)}
        rank("q", [long_row])
        assert len(seen[-1][1]) == MAX_CHARS
    finally:
        _predict = original
