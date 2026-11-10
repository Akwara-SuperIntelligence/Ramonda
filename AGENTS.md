# Working in this repository

Design and course material. The design is `EDA.md` and `ACHITECTURE.md` at the
root. `course/` is frozen reference. There is no implementation here yet.

## Rules

- **We consume Rakazo. We do not vendor its source.** Read its docs to answer a
  question about the agent; do not copy its code into this repository.
- The design lives in exactly two files: `EDA.md` (deployment and tenancy) and
  `ACHITECTURE.md` (the argument). When a decision changes, change the document
  in the same commit.
- Do not add a third design document. If something does not fit the two, it does
  not belong in the repo. Delete rather than branch into options.
- **Configure, then patch, then build.** Before adding a service, check whether a
  Rakazo environment variable or an MCP tool already does the job.
- `course/` is read-only reference. Do not edit, import, build, or deploy it.
- Use the vocabulary in `GLOSSARY.md`. Organisation, Space, and stamp have
  specific meanings; do not use them loosely.
- Never fork per customer. Shared cell, dedicated stamp, BYOC — one artifact set.

## Where to look

| Question | Document |
|---|---|
| How do we deploy and isolate Rakazo for a customer? | `EDA.md` |
| What is ours and what is Rakazo's? | `EDA.md` §1 |
| What does a term mean? | `GLOSSARY.md` |
| Why does the product work this way? | `ACHITECTURE.md` |
| How does Rakazo itself work? | Its own docs at `github.com/elie222/rakazo/tree/main/docs` |
| How was a mechanism demonstrated? | `course/lessons/` |

## Before you finish

- Every local link resolves: `make check`.
- A changed decision has a changed `EDA.md`.
- No new document, unless one of the two was deleted to make room.
