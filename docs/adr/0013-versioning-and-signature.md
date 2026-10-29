# A version is a settled edit, and a signature binds to a content hash

Status: accepted

A version is created when an edit burst settles — paragraph committed, or a short idle — not per raw keystroke. Each version stores the author, a semantic diff and the artifact hash. A Suggestion becomes a version only when a person accepts it, and that version records both the acceptor and the suggestion's origin. A signature binds `hash(artifact) + hash(evidence set) + hash(definition versions)`, and the document freezes: a post-signature change is an Addendum with its own signature, never an edit to a signed version.

Per-keystroke versioning produces thousands of unreadable versions and no meaningful unit of review. Binding the signature to the evidence and definition hashes is what makes it possible to say later exactly which rules and which sources produced the number that was signed.

## Consequences

- The Signer's own edits are ordinary versions authored by the Signer; signing is a separate, event-logged act.
- There is no state in which editing a document signs it.
