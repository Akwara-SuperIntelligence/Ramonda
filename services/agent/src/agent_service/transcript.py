"""The transcript as files: one JSONL object per turn.

Sources
    talk §05 — the transcript is memory; memory can be files
    EDA §8 — dated logs are files
    ADR 0008 — memory should not grow Postgres

Delta
    Messages leave the database. Each turn is one object under
    `memory/{org}/{conversation}/log/{seq}.jsonl`. A write replaces the entry
    with the same `(step, role)`, so a retry is a no-op.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_service import storage


def _prefix(org_id: str, conversation_id: str) -> str:
    return (
        f"memory/{storage._safe(org_id)}/{storage._safe(conversation_id)}/log/"
    )


def _key(org_id: str, conversation_id: str, seq: int) -> str:
    return f"{_prefix(org_id, conversation_id)}{seq:08d}.jsonl"


def _entries(key: str) -> dict[tuple[int, str], dict]:
    try:
        raw = storage.get_object(key)
    except storage.ObjectNotFound:
        return {}
    entries: dict[tuple[int, str], dict] = {}
    for line in raw.decode(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or "role" not in entry:
            continue
        entries[(int(entry.get("step", 0)), str(entry["role"]))] = entry
    return entries


def write_entry(
    org_id: str, conversation_id: str, seq: int, step: int, role: str, content: str
) -> None:
    key = _key(org_id, conversation_id, seq)
    entries = _entries(key)
    previous = entries.get((step, role))
    if previous is not None and previous.get("content") != content:
        return
    entries[(step, role)] = {
        "seq": seq,
        "step": step,
        "role": role,
        "content": content,
        "created_at": (
            previous.get("created_at")
            if previous
            else datetime.now(timezone.utc).isoformat()
        ),
    }
    body = "\n".join(
        json.dumps(entries[entry_key], sort_keys=True)
        for entry_key in sorted(entries)
    )
    storage.put_object(key, body.encode(), "application/x-ndjson")


def load(org_id: str, conversation_id: str, after_seq: int = -1) -> list[dict]:
    objects = storage.list_objects(_prefix(org_id, conversation_id))
    turn_keys = []
    for obj in objects:
        try:
            seq = int(Path(obj["key"]).stem)
        except ValueError:
            continue
        if seq > after_seq:
            turn_keys.append((seq, obj["key"]))
    out: list[dict] = []
    for _, key in sorted(turn_keys):
        entries = _entries(key)
        out.extend(entries[entry] for entry in sorted(entries))
    return out


def search(
    org_id: str, conversation_id: str, query: str, limit: int = 5
) -> list[dict]:
    needle = query.lower()
    hits = [
        entry
        for entry in load(org_id, conversation_id)
        if needle in str(entry.get("content", "")).lower()
    ]
    hits.sort(key=lambda entry: (entry.get("seq", 0), entry.get("step", 0)), reverse=True)
    return hits[:limit]


def delete_scope(org_id: str, conversation_id: str | None = None) -> int:
    prefix = (
        f"memory/{storage._safe(org_id)}/"
        if conversation_id is None
        else _prefix(org_id, conversation_id)
    )
    keys = [obj["key"] for obj in storage.list_objects(prefix)]
    storage.delete_keys(keys)
    return len(keys)


def purge(days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    keys = [
        obj["key"]
        for obj in storage.list_objects("memory/")
        if obj["last_modified"] < cutoff
    ]
    storage.delete_keys(keys)
    return len(keys)
