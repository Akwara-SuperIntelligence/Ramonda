# The hash is computed over one canonical JSON form

Status: accepted

The hash covers the event's canonical bytes: RFC 8785 JSON Canonicalisation Scheme — keys sorted, UTF-8, no insignificant whitespace, and no floating-point numbers. Integers and decimal strings only. The payload stays `jsonb` in its column; the canonical bytes are derived from it when the hash is computed and are never stored a second time.

JCS is a published standard with test vectors, so two writers cannot quietly disagree, and the event stays readable in `psql`. The no-float rule removes the one value type whose text form differs between implementations: a percentage or an amount is a decimal string, which is the shape a Calculation Record already carries (0045).

A binary encoding was rejected because an auditor with `psql` could not read the log. A per-module payload hash was rejected because it moves the same problem into eleven modules and makes the envelope depend on each module's discipline.

## Consequences

- A float in a payload is a bug, and the append refuses it.
- Canonicalisation lives in shared and has one implementation. Modules produce values, never bytes.
- The hash is over the logical event, so a `jsonb` round-trip cannot change it.
