# Backend-first, with our own enterprise authentication and a first-party client application

Status: accepted

Ramonda is a backend platform exposing an API. Identity is ours: the company runs its own enterprise authentication, and the client application signs users in through it. No third-party identity provider is the primary path.

The system is sold as a company's product, not as a script that runs inside someone's Drive. Owning identity is what lets clearance (0004) be evaluated against our object graph rather than being borrowed from an external directory.

## Consequences

- Authentication is a module with its own schema and public API, and the API contract is a deliverable in its own right.
- The workspace is consumed through the API; where its UI lives is a separate decision.
