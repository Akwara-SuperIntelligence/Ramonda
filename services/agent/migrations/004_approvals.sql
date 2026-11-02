create table if not exists approvals (
    id              text        primary key,
    org_id          text        not null,
    conversation_id text        not null,
    workflow_id     text        not null,
    action          text        not null,
    arguments       text        not null,
    status          text        not null default 'pending'
                    check (status in ('pending', 'approved', 'denied', 'expired')),
    created_at      timestamptz not null default now(),
    resolved_at     timestamptz
);
