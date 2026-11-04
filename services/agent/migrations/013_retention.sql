alter table effects add column if not exists org_id text;
alter table effects add column if not exists conversation_id text;
alter table outbox add column if not exists org_id text;
alter table outbox add column if not exists conversation_id text;

update outbox
set org_id = payload::jsonb ->> 'org_id',
    conversation_id = payload::jsonb #>> '{subject,conversation_id}'
where org_id is null and payload like '{%';

create index if not exists effects_scope on effects (org_id, conversation_id);
create index if not exists outbox_scope on outbox (org_id, conversation_id);
create index if not exists messages_created on messages (created_at);
create index if not exists model_calls_created on model_calls (created_at);
create index if not exists effects_created on effects (created_at);
create index if not exists inbox_received on inbox (received_at);
create index if not exists outbox_created on outbox (created_at);
create index if not exists approvals_created on approvals (created_at);
create index if not exists reviews_created on reviews (created_at);
create index if not exists tasks_created on tasks (created_at);
create index if not exists notifications_last on notifications (last_at);

create table if not exists deletions (
    id              bigserial   primary key,
    org_id          text        not null,
    conversation_id text        not null default '',
    deleted_at      timestamptz not null default now(),
    counts          jsonb       not null default '{}'
);

create index if not exists deletions_scope on deletions (org_id, conversation_id, deleted_at);
create index if not exists deletions_created on deletions (deleted_at);
