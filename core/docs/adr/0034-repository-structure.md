# Repository structure: shared core, generic shell, one package per client

Status: accepted

```
ramonda/
  GLOSSARY-MAP.md            # points at every glossary
  core/
    GLOSSARY.md              # platform vocabulary
    docs/adr/                # decisions that span modules
    identity/ access/ sources/ ingestion/ search/ evidence/
    ontology/ definitions/ artifacts/ jobs/ agents/ shared/
      docs/adr/              # decisions about that module
  platform/
    api/                     # app factory, middleware, auth wiring
    web/                     # editor + chat shell
  clients/
    <client>/
      app/
        composition.py       # assembles this client's deployment
        api/                 # this client's own endpoints
        web/                 # this client's own screens
      ontology/              # object types and links, in code
      definitions/           # rules and Procedure, in Python
      adapters/              # this client's source adapters
      skills/                # Markdown SOPs
      config/                # source bindings, allowlist, flags
      docs/
        adr/                 # decisions about THIS client
        GLOSSARY.md          # THIS client's vocabulary
      tests/
```

Five rules:

1. **The composition file is the only meeting point.** It may import core and its own client. Core never imports a client or a composition. A client never imports another client.
2. **A client's code lives in its folder.** If only one client needs it, it goes there. If two need it, it is proposed to core, and it enters core only domain-neutral (0027).
3. **A decision lives next to what it governs.** Cross-module decisions in `core/docs/adr/`; one module's decisions in `core/<module>/docs/adr/`; the shell's decisions in `platform/<app>/docs/adr/`; a client's decisions in `clients/<client>/docs/adr/`. Numbering is global, so cross-references keep working wherever a file sits.
4. **Client decisions and client vocabulary never leak upward.** `core/docs/adr/` and `core/GLOSSARY.md` carry only what holds for every client.
5. **Data never lives in the repo.** Jobs, artifacts, evidence, structure specs, templates and client documents live in the deployment's database and object storage.

## Consequences

- Adding a client is a new package plus a new deployment, not a fork. Ten clients are ten packages over one core.
- A core change must keep every client package building; the CI matrix runs each client's contract tests on every merge.
- Reading a module's decisions means reading its folder; there is no separate index to keep in sync.
