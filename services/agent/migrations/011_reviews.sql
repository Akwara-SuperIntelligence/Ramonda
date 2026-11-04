alter table approvals add column if not exists payload jsonb not null default '{}';

create table if not exists reviews (
    org_id          text        not null,
    conversation_id text        not null,
    run_id          text        not null,
    step            int         not null,
    tool            text        not null,
    argument        text        not null,
    verdict         text        not null
                    check (verdict in ('allow', 'deny', 'escalate')),
    reason          text        not null default '',
    prompt_version  text        not null default '',
    prompt_tokens   int         not null default 0,
    completion_tokens int       not null default 0,
    created_at      timestamptz not null default now(),
    primary key (org_id, conversation_id, run_id, step)
);
