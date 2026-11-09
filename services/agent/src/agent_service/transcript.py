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

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_service import storage


def _conv_prefix(org_id: str, conversation_id: str) -> str:
    return f"memory/{storage._safe(org_id)}/{storage._safe(conversation_id)}/"


def _prefix(org_id: str, conversation_id: str) -> str:
    return f"{_conv_prefix(org_id, conversation_id)}log/"


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


def _read_text(key: str) -> str:
    try:
        return storage.get_object(key).decode(errors="replace")
    except storage.ObjectNotFound:
        return ""


def _write_text(key: str, text: str) -> None:
    storage.put_object(key, text.encode(), "text/markdown")


def _profile_key(org_id: str, conversation_id: str) -> str:
    return f"{_conv_prefix(org_id, conversation_id)}profile.md"


def _tool_facts_key(org_id: str, conversation_id: str) -> str:
    return f"{_conv_prefix(org_id, conversation_id)}facts-tool.md"


def load_facts(org_id: str, conversation_id: str) -> tuple[list[str], list[str]]:
    """Return the user facts and the tool facts, in that order."""
    user = [
        line[2:].strip()
        for line in _read_text(_profile_key(org_id, conversation_id)).splitlines()
        if line.startswith("- ")
    ]
    tool = [
        line[2:].strip()
        for line in _read_text(_tool_facts_key(org_id, conversation_id)).splitlines()
        if line.startswith("- ")
    ]
    return user, tool


def add_fact(
    org_id: str, conversation_id: str, content: str, source: str
) -> None:
    """Append one fact to the profile or the tool-facts file. Duplicate safe."""
    key = (
        _profile_key(org_id, conversation_id)
        if source == "user"
        else _tool_facts_key(org_id, conversation_id)
    )
    line = "- " + " ".join(content.split())
    existing = _read_text(key).splitlines()
    if line in existing:
        return
    _write_text(key, "\n".join([*existing, line]) + "\n")


def _scratch_prefix(org_id: str, conversation_id: str) -> str:
    return f"{_conv_prefix(org_id, conversation_id)}scratch/"


def _scratch_key(org_id: str, conversation_id: str, effect_token: str) -> str:
    digest = hashlib.sha256(effect_token.encode()).hexdigest()[:16]
    return f"{_scratch_prefix(org_id, conversation_id)}{digest}.md"


def add_note(
    org_id: str, conversation_id: str, content: str, effect_token: str
) -> None:
    """One scratch object per effect token, so a retry replaces the same note."""
    _write_text(_scratch_key(org_id, conversation_id, effect_token), content)


def load_scratch(
    org_id: str, conversation_id: str, hours: int | None = 1
) -> list[dict]:
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=hours)
        if hours is not None
        else None
    )
    notes = []
    for obj in storage.list_objects(_scratch_prefix(org_id, conversation_id)):
        if cutoff is not None and obj["last_modified"] < cutoff:
            continue
        notes.append(
            {
                "content": _read_text(obj["key"]),
                "created_at": obj["last_modified"],
            }
        )
    notes.sort(key=lambda note: note["created_at"])
    return notes


def _plan_key(org_id: str, conversation_id: str) -> str:
    return f"{_conv_prefix(org_id, conversation_id)}plan.md"


def write_plan(org_id: str, conversation_id: str, text: str) -> None:
    _write_text(_plan_key(org_id, conversation_id), text)


def load_plan(org_id: str, conversation_id: str) -> str:
    return _read_text(_plan_key(org_id, conversation_id))


def reset_turn_state(org_id: str, conversation_id: str) -> None:
    """A new turn starts with no plan and no working summary."""
    storage.delete_keys(
        [
            _plan_key(org_id, conversation_id),
            _working_key(org_id, conversation_id),
        ]
    )


def _working_key(org_id: str, conversation_id: str) -> str:
    return f"{_conv_prefix(org_id, conversation_id)}working.json"


def write_working(
    org_id: str, conversation_id: str, text: str, seq: int, step: int
) -> None:
    _write_text(
        _working_key(org_id, conversation_id),
        json.dumps({"text": text, "seq": seq, "step": step}, sort_keys=True),
    )


def load_working(org_id: str, conversation_id: str) -> tuple[str, int, int]:
    try:
        data = json.loads(
            _read_text(_working_key(org_id, conversation_id)) or "{}"
        )
    except json.JSONDecodeError:
        return "", -1, -1
    return str(data.get("text", "")), int(data.get("seq", -1)), int(
        data.get("step", -1)
    )


def _summary_key(org_id: str, conversation_id: str) -> str:
    return f"{_conv_prefix(org_id, conversation_id)}summary.json"


def load_summary(org_id: str, conversation_id: str) -> tuple[str, int]:
    try:
        data = json.loads(_read_text(_summary_key(org_id, conversation_id)) or "{}")
    except json.JSONDecodeError:
        return "", -1
    return str(data.get("text", "")), int(data.get("seq", -1))


def write_summary(org_id: str, conversation_id: str, text: str, seq: int) -> None:
    _write_text(
        _summary_key(org_id, conversation_id),
        json.dumps({"text": text, "seq": seq}, sort_keys=True),
    )


def search(
    org_id: str, conversation_id: str, query: str, limit: int = 5
) -> list[dict]:
    needle = query.lower()
    hits = [
        entry
        for entry in load(org_id, conversation_id)
        if needle in str(entry.get("content", "")).lower()
    ]
    hits.sort(
        key=lambda entry: (entry.get("seq", 0), entry.get("step", 0)),
        reverse=True,
    )
    return hits[:limit]


def delete_scope(org_id: str, conversation_id: str | None = None) -> int:
    prefix = (
        f"memory/{storage._safe(org_id)}/"
        if conversation_id is None
        else _conv_prefix(org_id, conversation_id)
    )
    keys = [obj["key"] for obj in storage.list_objects(prefix)]
    storage.delete_keys(keys)
    return len(keys)


def purge(days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    keys = [
        obj["key"]
        for obj in storage.list_objects("memory/")
        if "/log/" in obj["key"] and obj["last_modified"] < cutoff
    ]
    storage.delete_keys(keys)
    return len(keys)


def purge_scratch(hours: int = 1) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    keys = [
        obj["key"]
        for obj in storage.list_objects("memory/")
        if "/scratch/" in obj["key"] and obj["last_modified"] < cutoff
    ]
    storage.delete_keys(keys)
    return len(keys)
