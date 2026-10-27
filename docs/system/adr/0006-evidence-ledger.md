# Mutable Case tables with an append-only Evidence ledger

Case state lives in ordinary mutable tables. Facts that must be provable live in `evidence`, which is append-only, hash-chained per Cell, and checkpointed with an Ed25519 signature. The application role has no `UPDATE` or `DELETE` grant on it.

We did not choose full event sourcing. Case state is projected and mutated in place because that is simpler to query and to migrate, and the audit obligation is satisfied by the ledger plus checkpoints. Event sourcing is a real commitment — every query, migration and refactor pays for it — and nothing in the product needs a rebuild-from-events yet.

The invariant that carries the value: **no number reaches a Decision without an evidence row naming its value, its Anchor, the Source that confirmed it, the extractor, and the Pack version.** A `Decision` cannot be constructed without a `Verified<T>`, and `Verified<T>` can only come from `rules::check`. The guarantee is in the type system, not in a review checklist.

The ledger grows into event sourcing later if a rebuild is ever needed; `case_event` already records transitions in order.
