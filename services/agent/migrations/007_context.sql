create table if not exists model_calls (
    org_id          text        not null,
    conversation_id text        not null,
    seq             int         not null,
    step            int         not null,
    model           text        not null,
    prompt_hash     text        not null,
    prompt_tokens   int         not null,
    cache_hit       int         not null,
    cache_miss      int         not null,
    completion_tokens int       not null,
    created_at      timestamptz not null default now(),
    primary key (org_id, conversation_id, seq, step)
);

create table if not exists conversations (
    org_id          text        not null,
    conversation_id text        not null,
    summary         text        not null default '',
    summary_seq     int         not null default -1,
    primary key (org_id, conversation_id)
);
