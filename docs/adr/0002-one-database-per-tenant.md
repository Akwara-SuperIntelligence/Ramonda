# One database per Tenant

Each Tenant gets its own PostgreSQL database, holding relational rows, vectors and keyword search. Every database has the same tables.

`tenant_id` still sits on every row, although the database holds one Tenant. A row that does not know its Tenant is a bug waiting for a bad restore, and merges or splits need the column as proof of what was whose.

Rejected: a shared database with `tenant_id` only (cheaper, but a bank's review becomes an audit of every query); a schema per Tenant in one database (migrations run N times, and isolation does not improve).

**Consequence:** a fleet of databases, each with its own backup, restore and migration run.
