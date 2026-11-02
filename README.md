# Ramonda Harness

Design and course material for an **always-on agent**: a colleague you can text
that keeps working after you close the laptop, survives restarts, remembers your
work, has its own computer, and asks before it does something irreversible.

This repository holds two things that share one vocabulary:

- **The course** — ten lessons that build the primitives one at a time, with toy
  but behaviourally accurate code in `build/`.
- **The real design** — the service as one part of a larger, event-driven,
  multi-tenant system that can also be deployed for a single customer.

The course teaches the mechanism. The design documents describe the product.

## The system

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
| [ACHITECTURE.md](ACHITECTURE.md) | Why the product works this way: the source talk, sections 01–06 | You want the reasoning, not the specification |
| [EDA.md](EDA.md) | Where the agent service ends, its contracts, dedupe, memory, tenancy, deployment profiles | You are designing or reviewing the agent service |
| [BUILD.md](BUILD.md) | Every service in the full system, with interfaces and definitions of done | You are building, staffing, or scoping a service |
| [LANGUAGE.md](LANGUAGE.md) | What is Rust, what is Python, and why | You are choosing a language or adding a service |
| [GLOSSARY.md](GLOSSARY.md) | The working vocabulary | You are unsure what a word means here |
| [reference/architecture-map.html](reference/architecture-map.html) | The product on one page | You are orienting, or printing something for a wall |
| [RESOURCES.md](RESOURCES.md) | Primary sources behind the claims | You want to check or go deeper |
| [MISSION.md](MISSION.md) | The course goal and its constraints | You are teaching or taking the course |
| [NOTES.md](NOTES.md) | Teaching notes and environment facts | You are running the course |

## Reading paths

**New to the project.** This page → [GLOSSARY.md](GLOSSARY.md) →
[reference/architecture-map.html](reference/architecture-map.html) →
[ACHITECTURE.md](ACHITECTURE.md) sections 01–04.

**Building the agent service.** [EDA.md](EDA.md) sections 1–5 and 7 →
[LANGUAGE.md](LANGUAGE.md) → lessons 01–04 → `build/lesson-03/server.py`.

**Building the sandbox.** [EDA.md](EDA.md) sections 1, 2, and 12 → lesson 08 →
`build/lesson-08/computer.py` → [BUILD.md](BUILD.md) section 6.3.

**Operating it.** [BUILD.md](BUILD.md) sections 3, 5, 8 → [EDA.md](EDA.md)
sections 9, 12.

**Reviewing the architecture.** [ACHITECTURE.md](ACHITECTURE.md) →
[EDA.md](EDA.md) → [BUILD.md](BUILD.md) → [LANGUAGE.md](LANGUAGE.md).

**Data and knowledge work.** [EDA.md](EDA.md) sections 8 and 11 →
[BUILD.md](BUILD.md) sections 6.4, 6.5.

## Repository layout

```
ACHITECTURE.md   source talk transcript
EDA.md           the agent service in the larger system
BUILD.md         full service inventory and definitions of done
LANGUAGE.md      Rust and Python decisions
GLOSSARY.md      vocabulary
MISSION.md       course goal and constraints
NOTES.md         teaching notes
RESOURCES.md     sources
reference/       one-page maps and the glossary as HTML
lessons/         ten course lessons
build/           course code, one directory per lesson
learning-records/  what the learner has demonstrated
assets/          styles and quiz script
```

## Vocabulary

Use the words in [GLOSSARY.md](GLOSSARY.md) precisely. The load-bearing ones:
**agent**, **harness**, **agent loop**, **turn**, **tool call**, **execution
state**, **durable execution**, **always-on agent**.

Terms that belong to the real design rather than the course — tenant, deployment
profile, shared cell, dedicated stamp, effect token, inbox and outbox — are
defined where they are first used in [EDA.md](EDA.md) and [BUILD.md](BUILD.md).

## Status

The design documents describe the target system. The production code does not
exist in this repository yet.

`build/` is course code: standard library only, one file per lesson, and
deliberately incomplete. Do not ship it. It exists to make the behaviour
concrete: the loop that dies, the journal, the server boundary, the router, the
cache meter, the sub-agent, the memory layers, the machine service, the review
gate, and the eval suite.

The lessons are the worked examples. [EDA.md](EDA.md) and [BUILD.md](BUILD.md) are
the specification. [ACHITECTURE.md](ACHITECTURE.md) is the argument.

## Conventions

- **One codebase, three deployment profiles.** Shared cell, dedicated stamp,
  BYOC. Never a fork per customer.
- **Document contracts and reasons, not internals.** The harness changes monthly;
  the envelope does not.
- **Python decides, Rust delivers.** Details in [LANGUAGE.md](LANGUAGE.md).
- **Events for facts, workflows for processes.** Details in [EDA.md](EDA.md)
  section 3.
- **Decisions get a one-page record** when they are expensive to reverse. The
  three canonical design documents stay the source of truth.
