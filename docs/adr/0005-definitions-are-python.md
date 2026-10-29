# Definitions are versioned Python functions, pinned by content hash — and so is the Procedure

Status: accepted

Every deterministic rule is a Python function `(inputs) -> result`, stored in the repository, reviewed like code, addressed by the hash of its content, and executed in a sandbox. No client-facing rule language in v0.1. The Codex Procedure is modelled with the same mechanism, because it must vary by committee and session type without code changes.

Arithmetic must be bit-identical and replayable, and a content hash makes every output attributable to an exact rule version.

## Consequences

- Old definition versions are never deleted: a re-run must reproduce the numbers an old document shipped with.
- The definition library is the moat and is an engineering artifact. A DSL becomes a v2 question, justified only by repeat definitions.
