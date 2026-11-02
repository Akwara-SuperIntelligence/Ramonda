create table if not exists inbox (
    event_id    text        primary key,
    org_id      text        not null,
    received_at timestamptz not null default now()
);
