# The core–client contract

Status: accepted

One sentence carries the whole relationship: **core has no knowledge of any client; a client has full knowledge of core.**

## Dependency direction

A client package may import any core module's public API. Core may never import a client, a client's composition, or any name from a client's vocabulary. There is exactly one meeting point — the client's `composition.py` — and it is loaded by the shell at startup. A client never imports another client.

This is enforced in CI by import-linter, so a violation fails the build rather than surviving in review.

## What a client supplies

Configuration (sources, allowlist, flags), its ontology in code, its definitions and Procedure in Python, its source adapters, its skills, its structure specs and templates as data, its own API endpoints and screens, and its composition file.

## What core may never contain

A client's name, a client's words ("Session", "covenant", "claim"), a client's data, a conditional branch for one client, or an endpoint that exists for one client. If a capability is needed by one client, it is a client module; if two clients need it, it is proposed to core and enters only in domain-neutral form (0027).

## The data boundary

Every deployment has its own database and object storage, and no client document or structure spec enters the repository (0022, 0007).

## The vocabulary and documentation boundary

`core/GLOSSARY.md` and `core/docs/adr/` hold only what is true for every client. A client's terms and a client's decisions live in `clients/<client>/docs/` (0034).

## The compatibility promise

A core change must keep every client package building; the CI matrix runs each client's contract tests on every merge. A breaking change to a core public API requires amending the system record that governs it before the client packages are touched.

## Consequences

- Adding a client never edits core, and adding a capability to core never names a client.
- The question "is this core or client?" has a mechanical answer: does every client need it, or does this one?
- A client package that needs core internals is evidence of a wrong boundary, not of a missing feature.
