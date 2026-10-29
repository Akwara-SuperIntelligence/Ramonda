# Every module carries a one-page contract in MODULE.md

Status: accepted

Each module has a `MODULE.md` beside its decisions:

```
core/<module>/docs/MODULE.md
core/<module>/docs/adr/
```

It answers five questions and nothing else:

1. What does this module do, and what does it refuse to do?
2. Its public API — the exact calls other modules may make.
3. What data it owns.
4. What events it publishes, and which it consumes.
5. Which modules it depends on.

For example, `shared` would say: it owns the event log, object storage and the model client, holds no business rules, publishes no domain events, and depends on nothing.

## Why

In a modular monolith the public API **is** the boundary. If that API lives only in code, the boundary is decided while typing, a caller must read your source to know what to call, and a violation is found in review or not at all. A one-page contract is reviewable in ten minutes and is what the code is then checked against.

## It is not an ADR

An ADR records why a choice was made; `MODULE.md` records what the module exposes and owns. [0031](../shared/docs/adr/0031-event-log.md) says the event log is shared infrastructure rather than a module; `MODULE.md` says what the append call looks like. The contract changes often, as the code grows. The ADR changes only when the choice changes.

## Order of work

Collect the system records that bind the module, settle what remains as the module's own ADRs, then write `MODULE.md` — writing it is where undecided questions surface — then implement. The contract is written before the code, not before the thinking.

## Limits

One page, five headings. A contract that cannot fit has a scope problem, not a formatting problem. The API may instead be expressed as `public.py` signatures, but then the boundary exists only once implementation starts, and the contract is preferred for that reason alone.

## Consequences

- A caller reads another module's `MODULE.md`, never its source.
- A module whose contract cannot be written in a page is too large and should be split or its boundary moved.
- When code and contract disagree, the code wins and the contract is corrected; if the disagreement was a real choice, it becomes an ADR.
