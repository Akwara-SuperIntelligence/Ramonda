# One image, pinned per Tenant, expand then contract

One image with three entrypoints (`api`, `worker`, `connector`). Each Tenant pins an image digest. Code, schema and Pack version independently: `0.1.x`, numbered migrations, and per-Tenant semver.

Migrations are forward-only and every one must be safe while the previous image is still running. A destructive change takes three releases: add, switch, drop. Rolling back means pinning the old digest, and the schema stays where it is.

No control plane in v0.1: a pinned `deployment.yaml` per Tenant and a script.

**Consequence:** a rollback never requires a migration rollback, which is the only reason rollbacks stay boring.
