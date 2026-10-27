# Modules

Six crates under `crates/<name>`. Each exposes types; behaviour arrives with the first vertical slice. Nothing here is a trait with one implementation, and nothing returns "not implemented" — a type that exists and a stub that lies are different things.

## Dependencies

```
agent   → corpus, rules, case
corpus  → identity, evidence
case    → rules, identity, evidence
rules   → (nothing)
evidence→ (nothing)
identity→ (nothing)
```

`scripts/check-boundaries.sh` fails the build on a forbidden edge. `case → rules` is the edge that matters: it is how a Decision can only be signed after every Check confirmed.

## `corpus` — how we read documents

Intake and retrieval in one module on purpose: both change when we learn to read a new format, and splitting them is how the previous system drifted (adr/0003).

```rust
pub struct Intake { source, source_ref, media_type }

pub struct Hit {
    document_version, breadcrumb, quote,
    page: Option<u32>,   // only where the document has printed pages
    score: f32,
}
```

One Anchor per Hit, and `page` is `None` rather than invented for a `.docx` (adr/0011).

## `agent` — how a use case reasons

The only module allowed to call a model.

```rust
pub enum Outcome {
    Drafted(Decision),
    Stopped(Vec<Discrepancy>),   // sources disagreed; a person sees both sides
    Escalated(String),
}
```

`Stopped` is a success, not an error. A Case that stops because two Sources disagree did exactly what the product promises.

## `rules` — how the client's rules are applied

```rust
pub enum Outcome { Suspicious, Routine, Escalate }
pub struct Decision { outcome, rationale }

pub fn confirm<T>(statuses: &[CheckStatus], decision: T) -> Option<Verified<T>>
```

`Verified<T>` has no public constructor, and `confirm` is the only function that makes one. It returns `None` if any Check is not `Confirmed`, **and if there are no Checks at all** — nothing verified is not a pass. Three tests cover exactly those three branches.

## `case` — what a piece of work is

```rust
pub enum State { Open, Running, Stopped, Drafted, Signed, Closed }
pub struct Trigger { source, source_ref }

pub enum Event {
    RunStarted, Stopped, Drafted,
    Signed { decision: Verified<Decision>, by: String },
}
```

`Event::Signed` requires a `Verified<Decision>`. A Decision cannot be signed if a Check did not run, and the compiler enforces it rather than a review checklist.

## `evidence` — what we must be able to prove

```rust
pub enum Entry { NumberAsserted, SourceConfirmed, RuleEvaluated, CheckFailed, HumanSigned, PackInstalled }

pub fn hash(prev: &str, entry: &Entry) -> String
```

Blake3 over the previous hash plus the entry. Editing one row breaks every later hash. No update or delete path exists, by construction.

## `identity` — who may see what

```rust
pub enum Classification { Public, Internal, Confidential, Restricted }
pub struct Caller { tenant, principal, groups, clearance }

impl Caller { pub fn may_see(&self, doc: Classification) -> bool }
```

The Tenant comes from the verified token, never from a request body. `may_see` is the single comparison every document query must use.

## Later, and only with a caller

Pack loading, model ports, database and job plumbing, the three process binaries, and the API. Each arrives with the vertical slice that needs it, not before.
