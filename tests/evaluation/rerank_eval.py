"""Measure rerank precision and nDCG on the labeled set and recommend a floor."""

import json
import math
import os
import time
from pathlib import Path

from ramonda.retrieval import rerank

LABELS = Path(__file__).with_name("labeled.jsonl")


def load():
    lines = [json.loads(line) for line in LABELS.read_text().splitlines() if line.strip()]
    texts = lines[0]["texts"]
    cases = []
    for row in lines[1:]:
        relevant = set(row["relevant"])
        cases.append(
            {
                "query": row["query"],
                "candidates": [
                    {"id": str(index), "text": text, "relevant": index in relevant}
                    for index, text in enumerate(texts)
                ],
            }
        )
    return cases


def metrics(ranked, positives, floor, k):
    kept = [row for row in ranked if row["score"] >= floor][:k]
    hits = sum(1 for row in kept if row["relevant"])
    precision = hits / len(kept) if kept else 0.0
    recall = hits / positives
    dcg = sum(
        (1 if row["relevant"] else 0) / math.log2(position + 2)
        for position, row in enumerate(kept)
    )
    ideal = sum(1 / math.log2(position + 2) for position in range(min(positives, k)))
    return precision, recall, dcg / ideal if ideal else 0.0


def evaluate(model):
    rerank.MODEL = model
    rerank._model = None
    cases = load()
    ranked = [(case, rerank.rank(case["query"], case["candidates"])) for case in cases]
    k = int(os.environ.get("RETRIEVAL_FINAL_K", "5"))
    rows = []
    for floor_pct in range(0, 100, 5):
        floor = floor_pct / 100
        values = [
            metrics(rows_, sum(c["relevant"] for c in case["candidates"]), floor, k)
            for case, rows_ in ranked
        ]
        precision = sum(value[0] for value in values) / len(values)
        recall = sum(value[1] for value in values) / len(values)
        ndcg = sum(value[2] for value in values) / len(values)
        rows.append((floor, precision, recall, ndcg))
    best = max(rows, key=lambda row: (round(row[3], 6), round(row[1], 6), -row[0]))
    print(f"model: {model}, queries: {len(cases)}, FINAL_K: {k}")
    print("floor  precision  recall  ndcg")
    for floor, precision, recall, ndcg in rows:
        print(f"{floor:.2f}   {precision:.3f}      {recall:.3f}   {ndcg:.3f}")
    print(
        f"recommended floor: {best[0]:.2f} "
        f"(precision {best[1]:.3f}, recall {best[2]:.3f}, ndcg {best[3]:.3f})"
    )

    pairs = [
        (case["query"], candidate["text"])
        for case in cases
        for candidate in case["candidates"]
    ]
    while len(pairs) < 100:
        pairs = pairs * 2
    pairs = pairs[:100]
    rerank._predict(pairs[:1])
    start = time.perf_counter()
    rerank._predict(pairs)
    elapsed = time.perf_counter() - start
    print(
        f"latency: {len(pairs)} pairs in {elapsed:.2f}s "
        f"({elapsed * 1000 / len(pairs):.1f} ms/pair)"
    )
    return best[0]


if __name__ == "__main__":
    for name in os.environ.get("EVAL_MODELS", rerank.MODEL).split(","):
        evaluate(name.strip())
