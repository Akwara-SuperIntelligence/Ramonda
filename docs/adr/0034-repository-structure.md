# Repository structure: shared core, generic shell, one package per client

Status: accepted

```
ramonda/
  core/                      # the eleven modules, domain-neutral
    identity/ access/ sources/ ingestion/ search/ evidence/
    ontology/ definitions/ artifacts/ jobs/ agents/ shared/

  platform/                  # the shell, written once
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
      tests/
```

Three rules:

1. **The composition file is the only meeting point.** It may import core and its own client. Core never imports a client or a composition. A client never imports another client.
2. **A client's code lives in its folder.** If only one client needs it, it goes there. If two need it, it is proposed to core, and it enters core only domain-neutral (0027).
3. **Data never lives in the repo.** Jobs, artifacts, evidence, structure specs, templates and client documents live in the deployment's database and object storage.

## Consequences

- Adding a client is a new package plus a new deployment, not a fork. Ten clients are ten packages over one core.
- A core change must keep every client package building; the CI matrix runs each client's contract tests on every merge.
- The client application is not a monolith-wide file: its endpoints and screens live with its package, and `platform/` holds only what is generic.
