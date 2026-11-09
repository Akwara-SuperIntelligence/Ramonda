"""Artifacts: bytes in object storage, facts in Postgres.

Sources
    BUILD §5 — the agent service owns its artifact bucket
    BUILD §6.2 — long tool output goes to object storage; the context gets a path
    AGENTS.md — long output goes to object storage, a path not a blob

Delta
    An opaque `artifact:{id}` reference, an S3-compatible backend with a local
    fallback for development and tests, and delete and retention by scope.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg

ARTIFACT_DAYS = 180
LOCAL_ROOT = Path(".agent")


class ObjectNotFound(Exception):
    """The object is missing."""


ArtifactNotFound = ObjectNotFound


def _dsn() -> str:
    return os.environ.get(
        "DATABASE_URL", "postgresql://ramonda:ramonda@127.0.0.1:5432/agent"
    )


def _safe(part: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", part) or "_"


def _bucket() -> str | None:
    return os.environ.get("S3_BUCKET") or None


def _key(org_id: str, conversation_id: str, sha: str) -> str:
    return f"artifacts/{_safe(org_id)}/{_safe(conversation_id)}/{sha}"


def _s3_client():
    import boto3  # imported only when the S3 backend is selected

    endpoint = os.environ.get("S3_ENDPOINT") or None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY") or None,
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY") or None,
        region_name=os.environ.get("S3_REGION", "us-east-1"),
        use_ssl=endpoint.startswith("https://") if endpoint else True,
    )


def put_object(key: str, data: bytes, content_type: str) -> None:
    bucket = _bucket()
    if bucket:
        _s3_client().put_object(
            Bucket=bucket, Key=key, Body=data, ContentType=content_type
        )
        return
    path = LOCAL_ROOT / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def get_object(key: str) -> bytes:
    bucket = _bucket()
    if bucket:
        from botocore.exceptions import ClientError

        try:
            return _s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404", "NotFound"):
                raise ObjectNotFound(key) from exc
            raise
    path = LOCAL_ROOT / key
    if not path.is_file():
        raise ObjectNotFound(key)
    return path.read_bytes()


def list_objects(prefix: str) -> list[dict]:
    bucket = _bucket()
    if bucket:
        client = _s3_client()
        out = []
        for page in client.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=prefix
        ):
            for item in page.get("Contents", []):
                out.append(
                    {
                        "key": item["Key"],
                        "last_modified": item["LastModified"],
                        "size": item["Size"],
                    }
                )
        return out
    base = LOCAL_ROOT / prefix
    if not base.exists():
        return []
    out = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        out.append(
            {
                "key": str(path.relative_to(LOCAL_ROOT)),
                "last_modified": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ),
                "size": stat.st_size,
            }
        )
    return out


def delete_keys(keys: list[str]) -> None:
    if not keys:
        return
    bucket = _bucket()
    if bucket:
        client = _s3_client()
        for start in range(0, len(keys), 1000):
            chunk = keys[start : start + 1000]
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": key} for key in chunk]},
            )
        return
    for key in keys:
        path = LOCAL_ROOT / key
        if path.is_file():
            path.unlink()


def _write(key: str, data: bytes, content_type: str) -> None:
    put_object(key, data, content_type)


def _read(key: str) -> bytes:
    return get_object(key)


def _delete_many(keys: list[str]) -> None:
    delete_keys(keys)


def put(
    org_id: str,
    conversation_id: str,
    name: str,
    content_type: str,
    data: bytes,
    run_id: str = "",
) -> str:
    """Store the bytes once and return an opaque artifact id."""
    sha = hashlib.sha256(data).hexdigest()
    key = _key(org_id, conversation_id, sha)
    _write(key, data, content_type)
    artifact_id = f"art_{uuid4().hex}"
    sql = (
        "insert into artifacts"
        " (id, org_id, conversation_id, sha256, name, content_type, size_bytes, run_id)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s)"
        " on conflict (org_id, conversation_id, sha256) do nothing returning id"
    )
    with psycopg.connect(_dsn()) as conn:
        cursor = conn.execute(
            sql,
            (
                artifact_id,
                org_id,
                conversation_id,
                sha,
                name,
                content_type,
                len(data),
                run_id,
            ),
        )
        row = cursor.fetchone()
        if row is None:
            cursor = conn.execute(
                "select id from artifacts"
                " where org_id = %s and conversation_id = %s and sha256 = %s",
                (org_id, conversation_id, sha),
            )
            row = cursor.fetchone()
    return row[0]


def get(artifact_id: str, org_id: str, conversation_id: str) -> tuple[dict, bytes]:
    """Return the metadata and bytes, or raise ArtifactNotFound."""
    with psycopg.connect(_dsn()) as conn:
        cursor = conn.execute(
            "select org_id, conversation_id, sha256, name, content_type, size_bytes"
            " from artifacts"
            " where id = %s and org_id = %s and conversation_id = %s",
            (artifact_id, org_id, conversation_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise ArtifactNotFound(artifact_id)
    org, conv, sha, name, content_type, size = row
    data = _read(_key(org, conv, sha))
    return (
        {
            "id": artifact_id,
            "name": name,
            "content_type": content_type,
            "size_bytes": size,
        },
        data,
    )


def delete_objects(org_id: str, conversation_id: str | None = None) -> int:
    """Delete the objects for a scope. Rows are left to the caller."""
    with psycopg.connect(_dsn()) as conn:
        if conversation_id is None:
            cursor = conn.execute(
                "select org_id, conversation_id, sha256, name from artifacts"
                " where org_id = %s",
                (org_id,),
            )
        else:
            cursor = conn.execute(
                "select org_id, conversation_id, sha256, name from artifacts"
                " where org_id = %s and conversation_id = %s",
                (org_id, conversation_id),
            )
        rows = cursor.fetchall()
    keys = [_key(org, conv, sha) for org, conv, sha, name in rows]
    _delete_many(keys)
    return len(keys)


def purge(days: int = ARTIFACT_DAYS) -> int:
    """Delete artifacts older than the window: objects first, then rows."""
    with psycopg.connect(_dsn()) as conn:
        cursor = conn.execute(
            "select id, org_id, conversation_id, sha256, name from artifacts"
            " where created_at < now() - (%s * interval '1 day')",
            (days,),
        )
        rows = cursor.fetchall()
    keys = [_key(org, conv, sha) for _, org, conv, sha, name in rows]
    _delete_many(keys)
    with psycopg.connect(_dsn()) as conn:
        conn.execute(
            "delete from artifacts where created_at < now() - (%s * interval '1 day')",
            (days,),
        )
    return len(rows)


def local_root() -> Path:
    return LOCAL_ROOT
