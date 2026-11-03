create table if not exists memories (
    id              bigserial   primary key,
    org_id          text        not null,
    conversation_id text        not null,
    kind            text        not null check (kind in ('fact', 'scratch')),
    content         text        not null,
    created_at      timestamptz not null default now()
);

create index if not exists memories_lookup
    on memories (org_id, conversation_id, kind, created_at desc);
