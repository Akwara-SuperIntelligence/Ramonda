# Working in this repository

Design and course material. `course/` is frozen reference; the design is
`ACHITECTURE.md` and `EDA.md` at the root. There is no implementation here yet.

## Rules

- The design lives in exactly two files: `ACHITECTURE.md` and `EDA.md`. When a
  decision changes, change the document in the same commit.
- Do not add a third design document. If something does not fit the two, it does
  not belong in the repo. Delete rather than branch into options.
- `course/` is read-only reference. Do not edit, import, build, or deploy it.
  Read it to understand a mechanism.
- Use the vocabulary in `GLOSSARY.md`.
- Never fork per customer. Shared cell, dedicated stamp, BYOC — one artifact set.
- The product is designed to be rewritten when the models change.

## Where to look

| Question | Document |
|---|---|
| Why does the product work this way? | `ACHITECTURE.md` |
| What are the agent service's contracts? | `EDA.md` |
| What does a term mean? | `GLOSSARY.md` |
| How was a mechanism demonstrated? | `course/lessons/` |
| What is on the agent's computer? | `EDA.md` §8 |

## Before you finish

- Every local link resolves: `make check`.
- A changed contract has a changed document.
