# Ramonda Harness

Always-on agents for organisations. We run [Rakazo](https://github.com/elie222/rakazo)
unmodified, one deployment per customer tier, and build the layers Rakazo does
not have: tenancy, provisioning, organisation knowledge, and upgrades.

Two things live here:

- **The design** — `EDA.md` is the deployment and tenancy contract,
  `ACHITECTURE.md` is the argument behind the product.
- **The course** — `course/` builds the primitives one at a time, with toy but
  behaviourally accurate code. It is frozen reference, not shipped code.

There is no implementation in this repository yet.

## The shape

```
                    customers' people
                           │
              ┌────────────┴────────────┐
              │   control plane (ours)  │  stamp inventory, org→stamp, domains
              └────────────┬────────────┘
                           │ one .env + override per stamp
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   shared cell        dedicated stamp      BYOC
   many orgs          one org              their cloud
   RLS by Space       own database         their keys
        │                  │                  │
        └────────── MCP: knowledge server ────┘
                   one credential per org
```

Three things are ours: the control plane, the knowledge service, and the
per-stamp configuration. Everything else — the agent loop, memory, approvals,
computers, channels, identity, audit, billing — is Rakazo's, and we do not fork
it. See [EDA.md](EDA.md) §1.

## Documents

| Document | Answers |
|---|---|
| [EDA.md](EDA.md) | How we deploy and isolate Rakazo for organisations |
| [ACHITECTURE.md](ACHITECTURE.md) | Why the product works this way: the source talk, sections 01–06 |
| [GLOSSARY.md](GLOSSARY.md) | What a term means |
| [reference/architecture-map.html](reference/architecture-map.html) | The product on one page |
| [course/RESOURCES.md](course/RESOURCES.md) | Primary sources behind the claims |

Reading path: this page → [GLOSSARY.md](GLOSSARY.md) → [EDA.md](EDA.md).

## Repository layout

```
README.md        this page
AGENTS.md        rules for AI agents working here
EDA.md           the deployment and tenancy contract
ACHITECTURE.md   the source talk: why the product works this way
GLOSSARY.md      vocabulary, shared by both tracks
compose.yaml     Postgres for development
Makefile         up, down, reset, check
scripts/         link check
reference/       one-page maps and the glossary as HTML
course/          frozen course material
```

Run `git config core.hooksPath .githooks` once, and every commit runs `make check`
before it is written.

`compose.yaml` is a local Postgres for developing our own services. It is not a
stamp. A stamp is generated from upstream Rakazo's Compose files, per
[EDA.md](EDA.md) §3.

## Status

`EDA.md` describes the target. Nothing here implements it. The earlier agent
service was deleted rather than fixed; Rakazo replaces it, and the layers in
`EDA.md` §3 and §5 are the work that remains.

`course/build/` is course code: standard library only, one file per lesson, and
deliberately incomplete. Do not ship it.

## Conventions

- **Consume Rakazo. Do not vendor it.** Their releases carry the fixes and build
  the six clients we would otherwise own. Configuration and MCP first; a patch
  only when both fail.
- **Configure before you patch, and patch before you build.** Every line of ours
  is maintained against their releases.
- **One Compose file, three profiles.** Shared cell, dedicated stamp, BYOC.
  Never a fork per customer.
- **Design lives in `EDA.md`.** If a decision changes, the document changes in
  the same commit.
- **`course/` is read-only.** Never import course code.
