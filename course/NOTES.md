# Teaching notes

## Preferences
- Python, 45–60 minute sessions, each with a small build step that runs.
- Wants to ship a personal always-on agent, not study the theory for its own sake.
- Has built LLM apps but not agent loops or long-running job infrastructure — do not assume durable-execution knowledge.
- Prefers concrete wins over completeness. Cut scope rather than lengthen a lesson.
- The model/harness split took several attempts. The framing that worked: "the model's whole world is the chat; the harness reads the files and puts one sentence in the chat." Use it early in later lessons.

## Code standards
- All code in this workspace follows `/ponytail` (full level): smallest complete change, no speculative flags or abstractions, deletion over addition, one small self-check for non-trivial logic. Say what was skipped, in one line, at the end of a reply.
- Build code should stay readable at a glance; prefer stdlib and what is already installed.

## Environment facts
- Repo root: `/Users/kulubyahassan/Developer/Akwara SuperIntelligence/Ramonda`.
- `.venv` was moved from `Ramonda-African-Union/`; the `pip` shim and `activate` script both hardcode the old path. `source .venv/bin/activate` puts a nonexistent directory on PATH, so bare `python` fails even though the prompt shows `(.venv)`. Use `.venv/bin/python` explicitly, or repair `activate` with a path substitution.
- `.env` has `DEEPSEEK_API_KEY` and `OPENROUTER_API_KEY`. A `deepseek-chat` call was verified working on 2026-10-30.
- `openai` 2.54.0 is installed in the venv.
- Source talk, sections 01–06 (Q&A not transcribed). Treat it as the primary source for the course's architecture claims.
