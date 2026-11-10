# Mission: Build an always-on agent

## Why
I want my own agent that keeps working after I close the laptop — a colleague I can text, that remembers our work, wakes up on events, and survives restarts. The architecture talk is the blueprint; I want to be able to build each piece, not just describe it.

## Success looks like
- A Python agent loop that calls tools and finishes a multi-step task on its own.
- The same agent runs on a server and resumes a half-finished task after the process is killed.
- It wakes from at least one trigger that is not me typing in a terminal (schedule, webhook, or chat message).
- It remembers me across sessions: a profile, dated work logs, and notes it writes for itself.
- It can use a sandboxed computer — run commands, browse — without touching my laptop.
- Irreversible actions (send, pay, delete) pass through a review/approval gate.
- I can defend each design choice against the alternatives in the talk and in the wider literature.

## Constraints
- Python 3.12, `openai` SDK against DeepSeek or OpenRouter (keys already in `.env`).
- Solo, part-time: 45–60 minute sessions, each ending with something running.
- Short lessons with one build step; no big-bang rewrite.
- No GPU, no model training. Buy or call models.

## Out of scope
- Training, fine-tuning, or serving my own model.
- A multi-tenant SaaS product with billing and org management (that is Ramonda's problem, not this mission's).
- Native mobile clients. A terminal or a chat bridge is enough.
- Rebuilding Temporal, Firecracker, or a browser-automation stack from scratch.
