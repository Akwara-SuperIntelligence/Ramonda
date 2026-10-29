# One schema and one database role per module, with no cross-schema joins

Status: accepted

Each module owns a Postgres schema and connects with its own role, which can read and write only that schema. Cross-schema joins are forbidden. This is the strongest enforcement available without splitting into services, and it turns a misplaced boundary into a permission error rather than a code review comment.

## Consequences

- A module that needs another module's data calls its public API and gets a snapshot.
- Migrations are per module and are owned by the module.
- Extracting a module into a service later means moving its schema with it.
