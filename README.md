# Ramonda Harness

Always-on agents for organisations. We run [Rakazo](https://github.com/elie222/rakazo)
unmodified, one deployment per customer tier, and build the layers Rakazo does
not have: tenancy, provisioning, organisation knowledge, and upgrades.

The design is `EDA.md`. There is no implementation in this repository yet.

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
| [GLOSSARY.md](GLOSSARY.md) | What a term means |
| [reference/glossary.html](reference/glossary.html) | The glossary as a page |

Reading path: this page → [GLOSSARY.md](GLOSSARY.md) → [EDA.md](EDA.md).

## Repository layout

```
README.md        this page
AGENTS.md        rules for AI agents working here
EDA.md           the deployment and tenancy contract
GLOSSARY.md      vocabulary
compose.yaml     Postgres for development
Makefile         up, down, reset, check
scripts/         link check
reference/       the glossary as HTML
```

Run `git config core.hooksPath .githooks` once, and every commit runs `make check`
before it is written.

`compose.yaml` is a local Postgres for developing our own services. It is not a
stamp. A stamp is generated from upstream Rakazo's Compose files, per
[EDA.md](EDA.md) §3. The development database is `ramonda`; `make reset` drops
it with the volume, and `make up` recreates it.

## Status

`EDA.md` describes the target. Nothing here implements it. The earlier agent
service was deleted rather than fixed; Rakazo replaces it, and the layers in
`EDA.md` §3 and §5 are the work that remains.

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
