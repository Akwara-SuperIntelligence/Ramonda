# One Cell per Tenant, one PostgreSQL per Cell

The default deployment is one Cell per enterprise: its own processes, its own database, provisioned by IaC, in our cloud account or in the client's. Pooled multi-tenancy exists only for pilots and small clients.

A bank's security review asks where the data is, who else is in the database, and whether it can be shown. With a Cell, the answer is a diagram of one deployment. Retrofitting that isolation later is a rewrite; building it now costs a Helm chart and a provisioning script.

Inside the Cell there is one PostgreSQL database holding relational rows, vectors and keyword search. No search cluster. The previous system ran PostgreSQL and OpenSearch side by side with two encoders for the same access policy — SQL and term filters — and they drifted, which is the failure this decision removes. A single store means access filtering happens once, in one transaction.

**Consequence:** `pg_search`-style BM25 is an extension and rules out stock managed PostgreSQL; the fallback is native full-text plus sparse vectors. Each Cell carries its own JWKS and its own host.
