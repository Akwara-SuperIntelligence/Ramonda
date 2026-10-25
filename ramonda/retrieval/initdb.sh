#!/bin/bash
# shortcut: image admin is postgres; only the retrieval login owns this schema
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=retrieval_password="$RETRIEVAL_DB_PASSWORD" <<'SQL'
CREATE ROLE retrieval LOGIN PASSWORD :'retrieval_password';
CREATE SCHEMA retrieval AUTHORIZATION retrieval;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA retrieval FROM PUBLIC;
ALTER ROLE retrieval SET search_path TO retrieval;
SQL
