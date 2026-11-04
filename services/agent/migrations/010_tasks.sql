create table if not exists tasks (
    id                 text        not null,
    org_id             text        not null,
    conversation_id    text        not null,
    description        text        not null,
    status             text        not null default 'running'
                       check (status in ('running', 'done', 'failed', 'stopped')),
    helper_workflow_id text        not null,
    report             text        not null default '',
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    primary key (org_id, conversation_id, id)
);
