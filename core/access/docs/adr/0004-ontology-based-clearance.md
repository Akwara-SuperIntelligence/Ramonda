# Clearance is evaluated on the typed object graph

Status: accepted

Permissions are granted on entities and relations in the typed object graph, and are inherited by any agent acting for a person. They are not granted on tables or endpoints. In v0.1 the ontology and the policy are small and the only subjects are two people, but the traversal and the permission shape are the real ones.

Building access control into the graph later means retrofitting every query, every retrieval filter and every agent tool. With one small client, doing it properly now is a few days of work and it is the foundation for every larger client.

In v0.1 the policy is permissive: both accounts may see every object, and no per-object rule narrows anything. The traversal exists anyway, so a later client can add a restriction without rewriting a single query or retrieval filter.

## Consequences

- The SQL filter step in retrieval is also the clearance step.
- The seed ontology is deliberately small; its exact node and relation set is still open.
