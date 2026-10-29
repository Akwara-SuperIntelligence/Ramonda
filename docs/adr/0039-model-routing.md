# A model per role, and one pinned embedding model per client

Status: accepted

Model choice is per specialist, configured by the workflow: cheap models for extraction and routine passes, the strongest reasoning models for the Analyst and Drafter, a long-context reader for the Editor. The client's deployment determines which providers are reachable, and all traffic leaves through one egress point (0007), so a no-external-inference client swaps models without a code change.

The embedding model is the exception. It is part of the index: change it and every stored vector is meaningless. It is pinned per client, recorded in the index metadata, and changing it is a re-embedding project with a migration, not a configuration edit.

## Consequences

- Role-to-model mapping is client configuration, so cost and quality can be tuned per deployment.
- Re-embedding is a planned operation that builds a second index and switches over; it never mutates the live one.
- Model choice is recorded in each Run, so a change in output quality can be traced to a change in model.
