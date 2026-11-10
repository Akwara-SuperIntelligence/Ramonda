# Ramonda Harness

Design and course material for an **always-on agent**: a colleague you can text
that keeps working after you close the laptop, survives restarts, remembers your
work, has its own computer, and asks before it does something irreversible.

Two things live here:

- **The course** — `course/` builds the primitives one at a time, with toy but
  behaviourally accurate code. It is frozen reference, not shipped code.
- **The design** — `ACHITECTURE.md` is the argument, `EDA.md` is the service
  contract.

There is no implementation in this repository yet.

## The target system

```
        clients: web, mobile, terminal, Slack, email
                            │
                       edge gateway
                            │
      ┌─────────────────────┼──────────────────────┐
      │                     │                      │
  agent service        approvals service      admin console
      │  (Temporal)
      ├── retrieval ──▶ HelixDB ◀── ingestion ◀── connectors
      ├── sandbox platform
      ├── secret broker and egress proxy
      └── LLM gateway
                            │
      Kafka ◀── outbox ─────┘        all services ──▶ telemetry
```

The agent service owns the loop: it consumes a command or an event, runs one
durable workflow per turn, calls the model and the tools, and emits a message
intent. Everything else is a separate service with its own contract
([EDA.md](EDA.md) §1).

## Documents

| Document | Answers |
|---|---|
| [ACHITECTURE.md](ACHITECTURE.md) | Why the product works this way: the source talk, sections 01–06 |
| [EDA.md](EDA.md) | Where the agent service ends, its contracts, dedupe, memory, tenancy, deployment profiles |
| [GLOSSARY.md](GLOSSARY.md) | What a term means |
| [reference/architecture-map.html](reference/architecture-map.html) | The product on one page |
| [course/RESOURCES.md](course/RESOURCES.md) | Primary sources behind the claims |
| [course/MISSION.md](course/MISSION.md) | The course goal and its constraints |
| [course/NOTES.md](course/NOTES.md) | Teaching notes and environment facts |

Reading path: this page → [GLOSSARY.md](GLOSSARY.md) →
[reference/architecture-map.html](reference/architecture-map.html) →
[ACHITECTURE.md](ACHITECTURE.md) §01–04 → [EDA.md](EDA.md).

## Repository layout

```
README.md        this page
AGENTS.md        rules for AI agents working here
ACHITECTURE.md   the source talk: why the product works this way
EDA.md           the agent service contract
GLOSSARY.md      vocabulary, shared by both tracks
compose.yaml     Postgres, Temporal, UI, and Redpanda for development
Makefile         up, down, reset, check
scripts/         link check
reference/       one-page maps and the glossary as HTML
course/          frozen course material
  lessons/       ten lessons
  build/         worked code, one directory per lesson
  learning-records/  what the learner has demonstrated
  assets/        styles and quiz script
```

## Status

`ACHITECTURE.md` and `EDA.md` describe the target system. Nothing here
implements it. An earlier first slice — a durable turn, a real model call, and
Postgres-backed conversation state — has been removed; the replacement is being
chosen and will be an open-source base rather than code written from scratch.

`course/build/` is course code: standard library only, one file per lesson, and
deliberately incomplete. Do not ship it. It exists to make the behaviour
concrete: the loop that dies, the journal, the server boundary, the router, the
cache meter, the sub-agent, the memory layers, the machine service, the review
gate, and the eval suite.

## Conventions

- **One codebase, three deployment profiles.** Shared cell, dedicated stamp,
  BYOC. Never a fork per customer.
- **Document contracts and reasons, not internals.** The harness changes monthly;
  the envelope does not.
- **Events for facts, workflows for processes.** Details in
  [EDA.md](EDA.md) §3.
- **`course/` is read-only.** Promote any detail you rely on into the design
  documents, then cite the lesson. Never import course code.
- **Prefer deleting a document to adding a fourth one.**
