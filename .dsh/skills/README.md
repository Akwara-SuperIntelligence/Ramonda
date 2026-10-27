# Agent skills

Matt Pocock's skill set, copied into this repo as editable files so they travel with
the code. Source: <https://github.com/mattpocock/skills> at commit `5beb35b`
(2026-10-19), MIT licensed — see [LICENSE-mattpocock-skills](./LICENSE-mattpocock-skills).

27 skills are installed. Twelve are model-invocable and appear in the agent's catalog.
Fifteen are user-invoked by design (`disable-model-invocation: true`): type `/name` in
a message to load one, for example `/to-spec`, `/to-tickets`, `/implement`, `/wait-what`.

`ponytail/` is not part of that set. It is this project's own laziness discipline and is
kept here so one directory holds every skill a session can see.

Not installed: `skills/misc` (4) and `skills/in-progress` (7) from upstream, which are
not part of the published set.

To update, either re-run the installer (`npx skills@latest add mattpocock/skills`) and let
it write into `.dsh/skills`, or copy the upstream `skills/engineering/*` and
`skills/productivity/*` directories over these, then check that every directory still has
a `SKILL.md` whose `name:` matches its folder.
