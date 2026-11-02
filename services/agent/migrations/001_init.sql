create table if not exists messages (
    org_id          text        not null,
    conversation_id text        not null,
    seq             int         not null,
    role            text        not null check (role in ('user', 'assistant')),
    content         text        not null,
    created_at      timestamptz not null default now(),
    primary key (org_id, conversation_id, seq, role)
);

create table if not exists effects (
    token      text        primary key,
    kind       text        not null,
    payload    text        not null,
    created_at timestamptz not null default now()
);
