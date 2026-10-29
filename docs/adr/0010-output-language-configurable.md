# Output language is client configuration; v0.1 ships English

Status: accepted

The artifact's output language is declared by the client, not fixed by the system. v0.1 ships English, and the first client's documents are produced in English. Documents may be ingested in any language regardless.

Producing an artifact in a language other than the source material is a correctness problem, not a toggle: a mistranslated Proposed Statement is worse than an English-only one. Each added output language therefore needs its own corroboration rule and its own evaluation cases, and it is a deliberate capability, not a switch.

## Consequences

- Multilingual ingestion must not assume English text in parsing, chunking or embedding.
- Terminology that must survive translation correctly — standard names, step citations, proposed wording — is marked in the client's configuration.
- A second output language is a project with evaluation cases, not a configuration flag flipped on.
