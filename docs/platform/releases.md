# Releases: one repo, many Tenants

There is one repository, one image, and one codebase. Every Tenant runs that image against its own database.

## Three things version independently

| Thing | Versioned as | Changes when |
|---|---|---|
| Code | image tag and digest, `0.1.x` | we ship behaviour |
| Schema | forward-only migrations, numbered | a table changes |
| Pack | semver, per Tenant | the Tenant's Workflows, Rules or Sources change |

Every Tenant's copy records all three, plus the image digest. A support question starts by asking for those four values.

## An upgrade is three steps

1. **Pin the new image digest and restart.** Code reaches every Tenant the same way: the same image, a different pin.
2. **Run migrations.**
3. **Install the new Pack**, if the Packs changed. A Pack install replays its fixtures first.

There is no per-Tenant build, no branch per Tenant, and no `if tenant ==`. If a Tenant needs behaviour that is not in the image, the answer is in its Pack.

## Migrations: expand, then contract

Migrations never roll back, so each one must be safe while the old code is still running. That means three releases, not one:

- **Release N**: add the column, backfill, leave the old column alone. Old code ignores it.
- **Release N+1**: switch reads and writes to the new column. Both still exist.
- **Release N+2**: drop the old column.

A destructive migration in the same release as the code that needs it is how a rollback turns into an outage.

## Rollout order

`dev` → AU → the rest. A bank gets a window they choose and a named contact.

The first Tenant is the canary. If it survives an hour of real traffic, the rest follow. One Tenant at a time, with the previous one pinned until the next one is healthy.

**Rolling back means pinning the old digest.** The schema stays at the new version. That is exactly why expand/contract exists: an image rollback must never need a migration rollback.

## What a rollout can break

- a migration that rewrites a large table and holds a lock;
- a Pack that a new schema no longer validates;
- a Run in flight when the image swaps. It must resume, and it finishes under the Workflow version it started with.

## No control plane in v0.1

Each Tenant has a small `deployment.yaml` in a private operations repository:

```yaml
tenant: au
image: registry.example/ramonda@sha256:...
database: au-prod
packs:
  au-reports: 1.3.0
```

A script applies it. That is the entire fleet tool: a pinned file and a loop over Tenants.

A fleet view belongs in v0.3. It reads versions. It does not hold credentials and it cannot reach into a Tenant's database.

## Tests that make this safe

- the API suite runs against a scratch schema built from the previous release;
- every migration runs twice in CI, which proves it is idempotent;
- every Pack replays its fixtures in CI;
- one end-to-end Run per Workflow, on the real Tenant, before it is marked upgraded.

## The rule that keeps this working

A difference between Tenants is data: a Workflow, a Rule, a Mapping, a Term.

If a difference cannot be expressed as data, that is a design bug in the platform. Fix the model for everyone, and test it against the second Tenant.

**The first `if tenant ==` is the fork.**
