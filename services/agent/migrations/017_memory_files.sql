-- Facts, scratch, and the summary moved to files.
-- profile.md, facts-tool.md, scratch/, summary.json live beside the transcript.
drop table if exists memories;
alter table conversations drop column if exists summary;
alter table conversations drop column if exists summary_seq;
