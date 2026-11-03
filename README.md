# Ramonda Harness

Design and course material for an **always-on agent**: a colleague you can text
that keeps working after you close the laptop, survives restarts, remembers your
work, has its own computer, and asks before it does something irreversible.

This repository holds two tracks that share one vocabulary:

- **The product** — `docs/` specifies it, `services/` will implement it. One
  service lives here: the agent service.
- **The course** — `course/` builds the primitives one at a time, with toy but
  behaviourally accurate code. It is frozen reference, not shipped code.

The course teaches the mechanism. `docs/` is the source of truth.

## The system

```
        clients: web, mobile, terminal, Slack, email
                            │
                       edge gateway (Rust)
                            │
      ┌─────────────────────┼──────────────────────┐
      │                     │                      │
  agent service        approvals service      admin console
      │  (Temporal)
      ├── retrieval ──▶ HelixDB ◀── ingestion ◀── connectors
      ├── sandbox platform (Rust)
      ├── secret broker and egress proxy
      └── LLM gateway
                            │
      Kafka ◀── outbox ─────┘        all services ──▶ telemetry
```

The agent service owns the loop: it consumes a command or an event, runs one
durable workflow per turn, calls the model and the tools, and emits a message
intent. Everything else is a separate service with its own contract.

## Documents

| Document | Answers | Read it when |
|---|---|---|
| [docs/ACHITECTURE.md](docs/ACHITECTURE.md) | Why the product works this way: the source talk, sections 01–06 | You want the reasoning, not the specification |
| [docs/EDA.md](docs/EDA.md) | Where the agent service ends, its contracts, dedupe, memory, tenancy, deployment profiles | You are designing or reviewing the agent service |
| [docs/BUILD.md](docs/BUILD.md) | Every service in the full system, with interfaces and definitions of done | You are building, staffing, or scoping a service |
| [docs/LANGUAGE.md](docs/LANGUAGE.md) | What is Rust, what is Python, and why | You are choosing a language or adding a service |
| [docs/CACHING.md](docs/CACHING.md) | Provider cache windows, minimums, and our measurements | You are tuning context or cost |
| [GLOSSARY.md](GLOSSARY.md) | The working vocabulary | You are unsure what a word means here |
| [reference/architecture-map.html](reference/architecture-map.html) | The product on one page | You are orienting, or printing something for a wall |
| [course/RESOURCES.md](course/RESOURCES.md) | Primary sources behind the claims | You want to check or go deeper |
| [course/MISSION.md](course/MISSION.md) | The course goal and its constraints | You are teaching or taking the course |
| [course/NOTES.md](course/NOTES.md) | Teaching notes and environment facts | You are running the course |

## Reading paths

**New to the project.** This page → [GLOSSARY.md](GLOSSARY.md) →
[reference/architecture-map.html](reference/architecture-map.html) →
[docs/ACHITECTURE.md](docs/ACHITECTURE.md) sections 01–04.

**Building the agent service.** [docs/EDA.md](docs/EDA.md) sections 1–5 and 7 →
[docs/LANGUAGE.md](docs/LANGUAGE.md) → course lessons 01–04 →
`course/build/lesson-03/server.py`.

**Building the sandbox.** [docs/EDA.md](docs/EDA.md) sections 1, 2, and 12 →
course lesson 08 → `course/build/lesson-08/computer.py` →
[docs/BUILD.md](docs/BUILD.md) section 6.3.

**Operating it.** [docs/BUILD.md](docs/BUILD.md) sections 3, 5, 8 →
[docs/EDA.md](docs/EDA.md) sections 9, 12.

**Reviewing the architecture.** [docs/ACHITECTURE.md](docs/ACHITECTURE.md) →
[docs/EDA.md](docs/EDA.md) → [docs/BUILD.md](docs/BUILD.md) →
[docs/LANGUAGE.md](docs/LANGUAGE.md).

**Data and knowledge work.** [docs/EDA.md](docs/EDA.md) sections 8 and 11 →
[docs/BUILD.md](docs/BUILD.md) sections 6.4, 6.5.

## Repository layout

```
README.md        this page
GLOSSARY.md      vocabulary, shared by both tracks
AGENTS.md        rules for AI agents working here
compose.yaml     Postgres, Temporal, UI, and Redpanda for development
Makefile         up, down, reset, test
docs/            the design: ACHITECTURE, EDA, BUILD, LANGUAGE, and adr/
reference/       one-page maps and the glossary as HTML
services/        the product. One directory per service
  agent/         the agent service, with its migrations
course/          frozen course material
  lessons/       ten lessons
  build/         worked code, one directory per lesson
  learning-records/  what the learner has demonstrated
  assets/        styles and quiz script
```

## Vocabulary

Use the words in [GLOSSARY.md](GLOSSARY.md) precisely. The load-bearing ones:
**agent**, **harness**, **agent loop**, **turn**, **tool call**, **execution
state**, **durable execution**, **always-on agent**.

Terms that belong to the real design rather than the course — tenant, deployment
profile, shared cell, dedicated stamp, effect token, inbox and outbox — are
defined where they are first used in [docs/EDA.md](docs/EDA.md) and
[docs/BUILD.md](docs/BUILD.md).

## Status

`docs/` describes the target system. `services/agent/` holds the first working
slice: a durable turn, a real model call, and Postgres-backed conversation state.
It is not production yet.
Production code does not exist yet.

`course/build/` is course code: standard library only, one file per lesson, and
deliberately incomplete. Do not ship it. It exists to make the behaviour
concrete: the loop that dies, the journal, the server boundary, the router, the
cache meter, the sub-agent, the memory layers, the machine service, the review
gate, and the eval suite.

The lessons are the worked examples. [docs/EDA.md](docs/EDA.md) and
[docs/BUILD.md](docs/BUILD.md) are the specification.
[docs/ACHITECTURE.md](docs/ACHITECTURE.md) is the argument.

## Conventions

- **One codebase, three deployment profiles.** Shared cell, dedicated stamp,
  BYOC. Never a fork per customer.
- **Document contracts and reasons, not internals.** The harness changes monthly;
  the envelope does not.
- **Python decides, Rust delivers.** Details in [docs/LANGUAGE.md](docs/LANGUAGE.md).
- **Events for facts, workflows for processes.** Details in
  [docs/EDA.md](docs/EDA.md) section 3.
- **`course/` is read-only.** Promote any detail you rely on into `docs/`, then
  cite the lesson. Never import course code.
- **Decisions get a one-page record** in `docs/adr/` when they are expensive to
  reverse. The four design documents stay the source of truth.
