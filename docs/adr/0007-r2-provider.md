# 0007 — Object storage provider: Cloudflare R2

Status: accepted. Configuration only; no code change.

## Context

ADR 0006 made the artifact store S3-compatible and left the provider open. The
agent serves artifacts that clients and evals read, so egress is the cost that
matters more than storage. The service must also run in three deployment
profiles, and BYOC means the customer's bucket.

## Decision

- **Default provider: Cloudflare R2.** Shared cell and dedicated stamps use R2.
- **BYOC:** the customer's S3-compatible bucket. Same code, different values.
- **Alternatives:** Backblaze B2 when egress stays under 3x storage; Wasabi at
  steady multi-terabyte volume; AWS S3 when the workers run in AWS, a customer
  requires it, or data residency demands a specific region.
- **Development and CI:** the local fallback under `.agent/artifacts`. No cloud
  cost and no service dependency.

R2 is chosen because egress is free and storage is cheaper than S3 Standard. The
access pattern is write once, read many: generated reports, CSV exports, long
tool output, eval reads. S3 charges about four times as much to serve a file once
as to store it for a month.

## Configuration

```
S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
S3_BUCKET=agent-artifacts
S3_REGION=auto
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
```

The endpoint is the only provider-specific value. `boto3` speaks the same S3 API
for R2, B2, Wasabi, S3, and LocalStack.

## Consequences

- No vendor lock-in: switching is an env change plus a bucket migration.
- R2 covers the subset we use: put, get, delete, list, and lifecycle. It does
  not cover every S3 feature; we do not use versioning, object lock, or
  presigned URLs.
- R2 has location hints rather than free region choice. Regulated customers use
  their own bucket or an in-region provider.
- The bucket needs a 180-day lifecycle rule to match the app purge.
- R2's free tier is 10 GB storage, 1M Class A, 10M Class B per month.

## Why not the others by default

- **B2:** cheapest storage, but downloads are free only up to 3x stored. Client
  downloads break that.
- **Wasabi:** flat and egress-free, but the 90-day and 1 TB minimums are wrong
  for small or short-lived artifacts.
- **S3:** best ecosystem and in-region latency, but egress dominates the bill
  for a read-many artifact store.
