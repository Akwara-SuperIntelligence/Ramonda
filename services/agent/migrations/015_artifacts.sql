create table if not exists artifacts (
    id              text        primary key,
    org_id          text        not null,
    conversation_id text        not null,
    sha256          text        not null,
    name            text        not null,
    content_type    text        not null,
    size_bytes      bigint      not null,
    run_id          text        not null default '',
    created_at      timestamptz not null default now(),
    unique (org_id, conversation_id, sha256)
);

create index if not exists artifacts_scope
    on artifacts (org_id, conversation_id, created_at);
create index if not exists artifacts_created on artifacts (created_at);
