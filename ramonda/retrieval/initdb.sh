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
SET ROLE retrieval;
CREATE TABLE retrieval.chunk (
    id text PRIMARY KEY,
    file_id text NOT NULL,
    parent_id text,
    kind text NOT NULL CHECK (kind IN ('text', 'table')),
    text text NOT NULL,
    breadcrumb text NOT NULL DEFAULT '',
    document_title text,
    section_summary text,
    prev_section_summary text,
    excerpt_keywords text,
    questions_this_excerpt_can_answer text
);
RESET ROLE;
SQL
