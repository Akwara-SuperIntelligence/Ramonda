alter table memories add column if not exists source text not null default 'user'
    check (source in ('user', 'tool'));

create table if not exists notifications (
    org_id          text        not null,
    conversation_id text        not null,
    last_at         timestamptz not null default now(),
    primary key (org_id, conversation_id)
);
