# The Procedure builds the document from rules, and stops at the signature

Status: accepted

When the Signer picks any Session, the system derives the document — its sections, its required documents and its deadlines — from the agenda plus Procedure rules, not from one fixed shell. Rules are of the form "an item at Step 5 gets Background / African Position / Rationale / Proposed statement / Recommendations"; "an item at Step 8 gets Position on adoption instead". The Author fixes only the exceptions.

The Procedure's scope ends at the signed document and its follow-ups. It does not model the session itself: no debate, no adoption procedure in the room, no final report drafting.

## Consequences

- A fixed shell was rejected because the first unusual Agenda Item would force a manual rebuild, and the shape would never generalise to a second committee.
- The Procedure is the second definition library after the rules; it is versioned and hash-pinned like code.
- Anything that happens after signature is outside the Procedure, so post-session work is a separate module, not a hidden stage.
