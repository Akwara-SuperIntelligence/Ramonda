#!/bin/bash
# shortcut: image admin is postgres; only the retrieval login owns this schema
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=retrieval_password="$RETRIEVAL_DB_PASSWORD" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE ROLE retrieval LOGIN PASSWORD :'retrieval_password';
CREATE SCHEMA retrieval AUTHORIZATION retrieval;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA retrieval FROM PUBLIC;
ALTER ROLE retrieval SET search_path TO retrieval, public;
SET ROLE retrieval;
SET search_path TO retrieval, public;
-- The order is the clearance order. Keep it equal to host.CLEARANCE.
CREATE TYPE retrieval.clearance AS ENUM ('public', 'internal', 'confidential', 'restricted');
CREATE TABLE retrieval.document (
    org_id text NOT NULL,
    file_id text NOT NULL,
    security_label retrieval.clearance NOT NULL,
    PRIMARY KEY (org_id, file_id)
);
CREATE TABLE retrieval.document_access (
    org_id text NOT NULL,
    file_id text NOT NULL,
    subject text NOT NULL,
    PRIMARY KEY (org_id, file_id, subject),
    FOREIGN KEY (org_id, file_id) REFERENCES retrieval.document (org_id, file_id) ON DELETE CASCADE
);
CREATE TABLE retrieval.chunk (
    id text NOT NULL,
    org_id text NOT NULL,
    file_id text NOT NULL,
    parent_id text,
    kind text NOT NULL CHECK (kind IN ('text', 'table')),
    text text NOT NULL,
    breadcrumb text NOT NULL DEFAULT '',
    document_title text,
    section_summary text,
    prev_section_summary text,
    excerpt_keywords text,
    questions_this_excerpt_can_answer text,
    -- shortcut: 1536 is text-embedding-3-small; change this when the embedding model is chosen. Null until save writes it.
    embedding vector(1536),
    -- The organisation is part of the key. The same text in two organisations is two rows.
    PRIMARY KEY (org_id, id),
    FOREIGN KEY (org_id, file_id) REFERENCES retrieval.document (org_id, file_id) ON DELETE CASCADE
);
CREATE INDEX chunk_embedding_hnsw ON retrieval.chunk USING hnsw (embedding vector_cosine_ops);
RESET ROLE;
SQL
