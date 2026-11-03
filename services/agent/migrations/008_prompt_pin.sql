alter table conversations add column if not exists prompt_version text not null default '';

alter table model_calls add column if not exists prompt_version text not null default '';
alter table model_calls add column if not exists hash_rules text not null default '';
alter table model_calls add column if not exists hash_tools text not null default '';
alter table model_calls add column if not exists hash_memory text not null default '';
