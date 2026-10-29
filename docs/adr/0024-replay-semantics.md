# Replay reconstructs a version from the event log, the definition hashes and the evidence hashes

Status: accepted

Replay never re-runs a model. It reconstructs any version of an artifact from three pinned things: the event log, the definition hashes and the evidence snapshot hashes. Every model call is recorded as an event carrying the hash of its input context, its full output and the tool calls it made. Because the model is not a pure function, its outputs are inputs to replay, not computations inside it.

The promise that survives this is the one that matters: given a signed document years later, the system can say exactly which rules, which sources and which model output produced each figure — without pretending the model would answer the same way twice.

## Consequences

- A model call that is not logged cannot contribute to a document that reaches SIGNED_OFF.
- The event log is therefore the system's primary record, not a debugging aid.
- Deterministic work stays deterministic: definitions still produce bit-identical output, and that is what makes their hashes meaningful.
