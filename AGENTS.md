# Working in this repository

Two tracks. `docs/` and `services/` are the product. `course/` is frozen
reference.

## Rules

- Product code lives in `services/`, one directory per service. The only service
  here is `services/agent`.
- Design lives in `docs/`. When a decision changes, change the document in the
  same commit as the code.
- `course/` is read-only reference. Do not edit, import, build, or deploy it.
  Read it to understand a mechanism, then implement the behaviour in
  `services/agent`.
- Use the vocabulary in `GLOSSARY.md`.
- Never fork per customer. Shared cell, dedicated stamp, BYOC — one artifact set.
- Prefer deleting code and documents to adding options. The product is designed
  to be rewritten when the models change.

## Where to look

| Question | Document |
|---|---|
| Why does the product work this way? | `docs/ACHITECTURE.md` |
| How is the agent service built? | `docs/EDA.md` |
| What services exist, and what must each do? | `docs/BUILD.md` |
| Which language, and why? | `docs/LANGUAGE.md` |
| What does a term mean? | `GLOSSARY.md` |
| How was a mechanism demonstrated? | `course/lessons/` |
| Where is the agent service now, and what is left? | `services/agent/STATUS.md` |

## Before you finish

- Every local link resolves.
- The definition of done in `docs/BUILD.md` §3 is met.
- A changed contract has a changed document.
