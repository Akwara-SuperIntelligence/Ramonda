# shared

One page. The primitives every module needs and none owns. It holds no business rules and never learns a client's word.

## What it does, and what it refuses

**It does:** records facts in the event log; stores files; carries model calls; is the only door to the internet; supplies the clock and ids; opens each module's database session and applies its migrations; holds the signing keys; queues background work; emits telemetry.

**It refuses:**

- a business word or a business rule — no Job, Run, Artifact, Figure, Session, Clearance;
- to interpret an event type or a payload;
- to decide what to fetch, keep, purge, enqueue or alert on;
- to read or write another module's schema;
- to write the log from a request path — appends arrive from a relay;
- to put client content in telemetry.

## Public API

**Event log** — `events`

- `append(events) -> list[int]` — the relay's call only. Assigns `sequence` and `hash`, chaining from the head. Idempotent by event id.
- `read(subject, from_sequence, to_sequence=None) -> list[Envelope]` — ordered, read-only, one subject.

**Storage**

- `put(data, media_type) -> BlobRef` — content-addressed; the ref carries the hash.
- `get(ref) -> bytes`
- `presign_get(ref, ttl) -> str`
- `delete(ref)` — the retention role only.

**Models**

- `complete(target, messages, tools=None) -> Answer` — the answer plus its receipt. No routing, no fallback, no logging.
- `embed(target, texts) -> list[Vector]`

**Egress**

- `request(request) -> Response` — the only outbound call, always through the proxy.

**Time and identity**

- `now() -> datetime` — UTC.
- `new_id() -> str` — UUIDv7.

**Database**

- `session(module) -> Session` — that module's own role.
- `migrate(module) -> None` — applies that module's revisions and records them.

**Keys**

- `sign(digest) -> Signature` — KMS-backed; the private key never enters the process.
- `verify(public_key, digest, signature) -> bool`

**Queue**

- `enqueue(name, payload, idempotency_key) -> str`
- `run_worker(handlers)` — started by the shell.

**Telemetry**

- `record(code, **fields)` — fields are ids, numbers, enums, durations, timestamps and error types. No free text.

**Relay**

- `run_relay(module, outbox)` — started by the shell. Reads that module's outbox with that module's session, calls `append`, marks the rows sent.

## What data it owns

- `events` schema: the `events` table, partitioned by month on `occurred_at`, and one chain head row.
- `shared` schema: `tasks` (the durable queue) and `migrations` (module, revision, applied_at).
- The bucket: content-addressed blobs, keyed by their hash.
- Nothing else. No telemetry store, no key material, no client configuration.

The envelope, whose shape shared owns:

```
id  type  version  subject  actor  occurred_at  sequence  payload  prev_hash  hash
```

- `subject` is empty for a system fact, otherwise a work item's id.
- `actor` is `person:<id>` or `system:<module>`.
- `occurred_at` is the writer's clock, `sequence` is the log's.
- `payload` holds the fact, including a model output. No floats.
- `hash` covers the RFC 8785 canonical bytes and includes `prev_hash`.

Every module creates an outbox table in its own schema, with shared's shape: `id, type, version, subject, actor, occurred_at, payload, sent_at`.

## What events it publishes and consumes

Publishes system facts only: `shared.key_rotated`, `shared.partition_retired`, `shared.relay_failed`. A system fact has no subject. No domain events.

Consumes none.

## What it depends on

No core module and no client package. Third-party libraries only: a Postgres driver, an S3 client, an HTTP client, a KMS client, a JSON canonicaliser and a telemetry exporter.
