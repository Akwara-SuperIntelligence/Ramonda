# A thing enters shared only if it could be published without a client

Status: accepted

Four tests, all required, decide whether something belongs in shared:

1. Two or more business modules need it.
2. It uses no business word — no Job, Run, Artifact, Session, Figure, Procedure, Clearance — and no module's entity.
3. It imports no module and knows no module's schema.
4. It could be published as a standalone library, useful to a project that has no Ramonda client.

The fourth test is the mechanical form of the other three. If shared needed to know what a Job is, or how a Run is stored, it could not be published alone. That makes the membership argument checkable instead of a matter of taste.

Examples: object storage passes all four. The model transport passes all four. Observability passes all four. The Figure check fails test 2, because it uses Figures. Object storage *of* a Structure Spec passes; the Structure Spec itself does not.

## Consequences

- The "what it refuses to do" section of `MODULE.md` is these four tests read backwards.
- A proposal that fails test 2 belongs to a module, however small.
- A proposal that fails test 1 is premature: wait for the second caller.
- "Is it important?" is the wrong question. The right one is "does it decide anything about the business?"
