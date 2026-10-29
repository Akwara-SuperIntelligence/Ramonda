# One compose file, one VM, five pieces

Status: accepted

A deployment is: an API container, a worker container, Postgres, an S3-compatible bucket, and an egress proxy — started from one compose file on one VM in the client's cloud account. Nightly backups with thirty days of point-in-time recovery.

The egress proxy is mandatory. It is the only route to models and the internet, and it is what turns "no external inference" into a deployment setting rather than a code change.

Kubernetes is not used until a client forces it. A regulated office with two users does not need an orchestrator; it needs a deployment it can reason about.

## Consequences

- Single-tenant isolation (0007) is physical: one VM, one database, one bucket per client.
- Restore is a rehearsed procedure, not a hope: a backup that has never been restored is not a backup.
- Scaling starts vertically; the fan-out (0035) is bounded by worker concurrency, which is a setting.
