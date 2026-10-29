# A large payload is accepted and alerted

Status: accepted

An append whose payload exceeds the 1 MB trigger (0056) succeeds. Shared emits a telemetry alert carrying the event type, the size and the subject, so the measurement reaches a person.

Refusing the append would lose a Run's work to protect a limit that exists only to schedule a review. The limit is a measurement, not a rule. Silent truncation would corrupt the record, which is worse than either.

## Consequences

- The trigger's consequence is a decision to revisit 0056, not a failure of the work.
- The alert carries no payload content (0058): a type, a size, an id and a subject.
- Payload size is measured on every append, so the distribution is known before it becomes a problem.
