create table if not exists routines (
    id              text        primary key,
    org_id          text        not null,
    conversation_id text        not null,
    cron            text        not null,
    timezone        text        not null default 'UTC',
    text            text        not null,
    enabled         boolean     not null default true,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists routines_scope on routines (org_id, conversation_id);
create index if not exists routines_enabled on routines (enabled) where enabled;
