# Course material

Frozen reference. This tree is not built, not deployed, and not imported by
`services/`.

It exists because the mechanism is easier to see in 200 lines of standard
library Python than in a production service. Read it to understand a behaviour,
then implement that behaviour in `services/agent`.

## Contents

| Path | What it is |
|---|---|
| `lessons/` | Ten lessons, one mechanism each |
| `build/` | Worked code, one directory per lesson, standard library only |
| `learning-records/` | What the learner demonstrated, and when |
| `assets/` | Styles and the quiz script |
| `MISSION.md` | The course goal and its constraints |
| `NOTES.md` | Teaching notes and environment facts |
| `RESOURCES.md` | Sources behind the claims |

## Lesson map

| Lesson | Mechanism | Product component |
|---|---|---|
| 01 The loop that dies | Agent loop and tool call | Harness |
| 02 Write it down before you do it | Journal, replay, recovery | Durable execution |
| 03 The process is not the agent | Thin client, thick server, `send_user` | Edge and agent boundary |
| 04 Wake on events | Triggers, dedupe, priority, batching, silence | Consumer and router |
| 05 Stay lean | Prompt cache, compaction, tool search, files | Context assembly |
| 06 Delegate | Sub-agents with fresh context | Child workflows |
| 07 Remember | Profile, dated logs, scratchpad, skills | Memory layers |
| 08 Give it a machine | Machine as a service, reset, snapshot | Sandbox platform |
| 09 Trust it | Auto-review, injection, approvals, secrets | Policy and gates |
| 10 Get better | Evals, inner and outer loops | Evals service |

## Rules for this tree

- Standard library only. No new dependencies.
- One file per lesson, small enough to read in one sitting.
- Deliberately incomplete. The gaps are the lesson.
- No production imports. Nothing here may be imported by `services/`.

## Where to go next

The specification is in `docs/EDA.md` and `docs/BUILD.md`. The argument is
`docs/ACHITECTURE.md`.
