# Client data never enters the repository, and the document structure is learned from the client's documents

Status: accepted

Ramonda connects to a client's sources and ingests into the client's deployment. Customer documents are never committed to the repository, and no test fixture is built from them. The structural specification (0018) and the Procedure are derived from the client's own documents inside the client's deployment, not encoded in the codebase. The golden case is a configuration that points at the client's data, not files in the repo.

This is the same rule that makes single-tenant deployment (0007) meaningful: if the repo held client documents, the isolation would be fiction.

## Consequences

- Structural checks learn from the ingested examples at runtime and store what they learned as client-scoped configuration, versioned like everything else.
- Tests that need real documents run only inside a client deployment.
- The repository can be shared, open-sourced or moved to a new machine without leaking anyone's data.
