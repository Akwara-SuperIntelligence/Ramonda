create table if not exists outbox (
    id           text        primary key,
    topic        text        not null,
    payload      text        not null,
    published_at timestamptz,
    created_at   timestamptz not null default now()
);

create index if not exists outbox_unpublished on outbox (created_at) where published_at is null;
