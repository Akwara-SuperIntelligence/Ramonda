# One deployment per client; one Postgres with pgvector; one model egress point

Status: accepted

Each client gets their own deployment in their own cloud account: one Postgres (pgvector for embeddings), one S3-compatible document store, no shared data plane between clients. Every model call leaves through a single egress point so an in-perimeter model can be substituted without touching modules.

Cross-client data co-residence is unrecoverable with a regulator. Model optionality must be a property of the architecture from the start, not a later porting project.

## Consequences

- Connector reuse means code and configuration, not infrastructure.
- Multi-tenancy, if ever, is a cost optimisation justified by unit economics.
