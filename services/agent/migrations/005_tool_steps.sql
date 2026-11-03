alter table messages add column if not exists step int not null default 0;

alter table messages drop constraint if exists messages_pkey;
alter table messages add primary key (org_id, conversation_id, seq, step, role);

alter table messages drop constraint if exists messages_role_check;
alter table messages add constraint messages_role_check
    check (role in ('user', 'assistant', 'tool'));
