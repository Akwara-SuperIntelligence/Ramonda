create table if not exists conversation_locks (
    org_id          text        not null,
    conversation_id text        not null,
    workflow_id     text        not null,
    expires_at      timestamptz not null,
    primary key (org_id, conversation_id)
);
