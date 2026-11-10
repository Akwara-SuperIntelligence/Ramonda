# Working in this repository

Design material. The design is `EDA.md` at the root. There is no implementation
here yet.

## Rules

- **We consume Rakazo. We do not vendor its source.** Read its docs to answer a
  question about the agent; do not copy its code into this repository.
- The design lives in one file: `EDA.md`. When a decision changes, change it in
  the same commit.
- Do not add a second design document. If something does not fit, it does not
  belong in the repo. Delete rather than branch into options.
- **Configure, then patch, then build.** Before adding a service, check whether a
  Rakazo environment variable or an MCP tool already does the job.
- Use the vocabulary in `GLOSSARY.md`. Organisation, Space, and stamp have
  specific meanings; do not use them loosely.
- Never fork per customer. Shared cell, dedicated stamp, BYOC — one artifact set.
- **`main` is protected.** Work on a branch and open a pull request; a direct
  push is rejected. The `links` check must pass before merge.
- **No LICENSE file.** This is a company repository, not an open-source project.
  Do not add a licence, and do not invite contributions.

## Where to look

| Question | Document |
|---|---|
| How do we deploy and isolate Rakazo for a customer? | `EDA.md` |
| What is ours and what is Rakazo's? | `EDA.md` §1 |
| What does a term mean? | `GLOSSARY.md` |
| How does Rakazo itself work? | Its own docs at `github.com/elie222/rakazo/tree/main/docs` |

## Before you finish

- Every local link resolves: `make check`.
- A changed decision has a changed `EDA.md`.
- No new document. `EDA.md` is the design.
