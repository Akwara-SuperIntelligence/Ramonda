DO $$
BEGIN
  CREATE ROLE ramonda_app LOGIN PASSWORD 'ramonda_app';
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS audit_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  recorded_at text NOT NULL,
  actor_subject text NOT NULL,
  actor_username text NOT NULL,
  action text NOT NULL,
  arguments jsonb NOT NULL,
  previous_hash text NOT NULL,
  hash text NOT NULL,
  CONSTRAINT audit_log_previous_hash_key UNIQUE (previous_hash),
  CONSTRAINT audit_log_hash_key UNIQUE (hash),
  CONSTRAINT audit_log_previous_hash_len CHECK (char_length(previous_hash) = 64),
  CONSTRAINT audit_log_hash_len CHECK (char_length(hash) = 64)
);

REVOKE ALL ON TABLE audit_log FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_log FROM ramonda_app;
GRANT SELECT, INSERT ON TABLE audit_log TO ramonda_app;
GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO ramonda_app;
