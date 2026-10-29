# Every line names an actor, and the actor belongs to the client

Status: accepted

Each event carries one actor: a person id for anything a person started, or `system:<module>` for a machine act such as a relay append, a retention sweep or a key rotation. An agent run is the person's act, because Clearance is inherited (0004), and the Run id sits in the payload.

The actor exists for the client, not for us. It is what lets the client answer, years later, who let a Figure through and who signed the Artifact (0006, 0013). Ramonda does not read the actor to measure its own service; that is telemetry's job (0058), and the two must not be mixed.

## Consequences

- An audit screen can name a person for every human act without a join to another system.
- `system:` events are the only ones without a person, and the prefix makes them countable.
- Using the log for product analytics is a change of purpose and needs an ADR, because the client's record would then be serving someone else's question.
