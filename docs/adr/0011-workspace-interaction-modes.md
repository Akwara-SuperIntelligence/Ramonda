# The workspace has three interaction modes and per-person permission levels

Status: accepted

The artifact workspace behaves like the reference editor the customer showed: a document pane and an agent panel side by side. A person is always in exactly one interaction mode — Editing, Suggesting or Viewing — and their permission level decides which modes are available to them. In Suggesting mode the person's changes become Suggestions, not artifact content. The agent panel accepts skills, `@`-references to documents and requirements, and plain chat.

The mode boundary is what makes the audit trail meaningful: a suggestion is not an edit, and the difference must be visible in the document, not inferred from a log.

## Consequences

- The three modes are one state machine, persisted per person per document.
- Suggestions must be visually distinct in the document and listable as a review surface.
- Viewing mode is the Signer's default before signing.
