# 0006 — Object storage for artifacts

Status: accepted. Built for long tool output and file reads only.

## Context

Long tool output was written to local `.agent/artifacts` and read back by a
local path. That breaks across replicas and containers, and it puts bytes on a
disk that dies with the process. BUILD §5 gives the agent service its own
artifact bucket. BUILD §6.2 says long output goes to object storage and the
context gets a path. The chat file cards in the design discussion are a channel
feature, not this decision.

## Decision

### Backend

- S3-compatible storage via `boto3`, configured by `S3_ENDPOINT`,
  `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, and `S3_REGION`.
- A **local filesystem fallback** under `.agent/artifacts` when `S3_BUCKET` is
  not set. Development and tests use it. It is not a production backend.
- MinIO's public images now require authentication, so compose does not ship a
  local S3 service. Point `S3_*` at a real bucket, or leave it unset for the
  fallback. The S3 adapter was live-checked against LocalStack 3.8.

### Data model

- `artifacts` table: `id`, `org_id`, `conversation_id`, `sha256`, `name`,
  `content_type`, `size_bytes`, `run_id`, `created_at`.
- Unique `(org_id, conversation_id, sha256)`.
- Key: `artifacts/{org_id}/{conversation_id}/{sha256}`. Content-addressed, no
  filename in the key. The same bytes are one object and one row.
- The context, messages, and events carry an **opaque** `artifact:{id}`, never
  an S3 URL. `get` checks `org_id` and `conversation_id` before it returns bytes.

### Write and read

- `_effect` stores output longer than `SIZE_LIMIT` and returns a preview plus
  `artifact:{id}`.
- `read_file` accepts `artifact:{id}`, resolves the row, checks scope, and
  returns a 4000-character slice. The old bare-name local path stays for legacy
  development files.

### Deletion and retention

- `delete_scope` deletes the scope's objects before it deletes rows. An object
  delete failure leaves the rows for a retry.
- `purge` deletes artifacts older than **180 days**: objects first, then rows.
- The bucket needs a lifecycle rule for the same window. That is deployment
  configuration, not application code.

## Consequences

- Bytes stay out of Postgres and out of the model context.
- One writer: the agent service owns its bucket. Channels must not write it.
- Deletion now spans two stores. The order is object first, rows second.
- The local fallback is a test convenience. A production deployment that forgets
  `S3_BUCKET` writes to ephemeral disk.

## Deferred

- Inbound attachments: the channel or ingestion stores them and passes a
  reference. That contract is not written yet.
- Outbound attachment cards and a read endpoint. Channels need a way to fetch
  bytes through the agent service.
- Binary generation (`docx`, `xlsx`, images). That is the sandbox.
- Presigned URLs. They leak scope and expire; a service read path is better.
- Bucket provisioning and IAM. That is platform work.
