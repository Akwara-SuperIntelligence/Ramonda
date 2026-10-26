"""Index chunks and run BM25 in OpenSearch. Private to retrieval."""

import json
import os
import urllib.error
import urllib.request

INDEX = "chunks"

_MAPPING = {
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "org_id": {"type": "keyword"},
            "file_id": {"type": "keyword"},
            "parent_id": {"type": "keyword"},
            "kind": {"type": "keyword"},
            "text": {"type": "text"},
            "breadcrumb": {"type": "text"},
            "document_title": {"type": "text"},
            "excerpt_keywords": {"type": "text"},
            "questions": {"type": "text"},
            "security_label": {"type": "keyword"},
            "access": {"type": "keyword"},
            "doc_date": {"type": "date"},
            "doc_type": {"type": "keyword"},
            "department": {"type": "keyword"},
        }
    }
}

# The enriched fields carry the terms the body does not. Weights are tunable.
_FIELDS = ["document_title^3", "excerpt_keywords^3", "questions^2", "text", "breadcrumb"]

_ready = False


def _request(method, path, body=None, ndjson=None):
    base = os.environ.get("OPENSEARCH_URL", "http://127.0.0.1:9200").rstrip("/")
    data = None
    headers = {}
    if ndjson is not None:
        data = ndjson.encode("utf-8")
        headers["Content-Type"] = "application/x-ndjson"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


def _ensure():
    global _ready
    if _ready:
        return
    try:
        _request("HEAD", f"/{INDEX}")
    except urllib.error.HTTPError as err:
        if err.code != 404:
            raise
        _request("PUT", f"/{INDEX}", _MAPPING)
    _ready = True


def index(records):
    if not records:
        return
    _ensure()
    lines = []
    for record in records:
        lines.append(json.dumps({"index": {"_index": INDEX, "_id": f"{record['org_id']}|{record['chunk_id']}"}}))
        lines.append(json.dumps(record))
    # shortcut: refresh=true makes a save visible at once; turn it off when ingest writes large batches.
    response = _request("POST", "/_bulk?refresh=true", ndjson="\n".join(lines) + "\n")
    if response.get("errors"):
        raise RuntimeError("OpenSearch bulk index failed")


def search(query, filters, limit):
    _ensure()
    body = {
        "size": limit,
        "query": {
            "bool": {
                "filter": filters,
                "must": {
                    "multi_match": {
                        "query": query,
                        "fields": _FIELDS,
                        "type": "best_fields",
                    }
                },
            }
        },
    }
    response = _request("POST", f"/{INDEX}/_search", body)
    return [
        {
            "id": hit["_source"]["chunk_id"],
            "file_id": hit["_source"].get("file_id"),
            "kind": hit["_source"].get("kind"),
            "text": hit["_source"].get("text"),
            "breadcrumb": hit["_source"].get("breadcrumb"),
            "document_title": hit["_source"].get("document_title"),
            "excerpt_keywords": hit["_source"].get("excerpt_keywords"),
            "questions": hit["_source"].get("questions"),
            "score": hit["_score"],
        }
        for hit in response["hits"]["hits"]
    ]
