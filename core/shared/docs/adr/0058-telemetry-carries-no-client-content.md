# Telemetry never carries client content, and has no field for it

Status: accepted

A telemetry record is a code plus typed fields: ids, counts, durations, byte sizes, booleans, enums, timestamps, a model name, an error type. It has no free-text field. The message is a code such as `relay.lag`, and the detail is in the fields.

This is structural, not a policy note. A rule that says "do not log the prompt" survives until the first hard bug. A record whose shape cannot hold a prompt survives the bug, because there is nowhere to put it.

Client content means document text, prompts, model answers, Figure values, names, email addresses and file names. Ids are allowed: they identify a row without describing it.

## Consequences

- Debugging starts from an id or a code and continues in the log or the audit screen. Telemetry is the entry point, never the copy.
- Error detail is an error type, a stack trace and a correlation id. A stack trace is our code, not the client's data.
- An exception to this rule needs an ADR, not a code review comment.
