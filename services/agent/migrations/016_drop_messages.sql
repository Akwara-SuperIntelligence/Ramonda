-- Messages moved to the file transcript (services/agent/src/agent_service/transcript.py).
-- The table is no longer read or written. Drop it so Postgres stays small.
drop table if exists messages;

-- The turn counter must survive transcript retention. If it came from the files,
-- a purge would reset it and reuse an old seq. The workflow id makes a retry
-- return the same seq instead of skipping one.
alter table conversations add column if not exists last_seq int not null default -1;
alter table conversations add column if not exists last_workflow_id text not null default '';
