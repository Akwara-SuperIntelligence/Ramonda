# An event type is `<module>.<fact>` with a version

Status: accepted

Each event declares a type such as `jobs.submitted`, `agents.model_call`, `artifacts.version_created`, and an integer version that starts at 1. The module that publishes the fact owns the type and the shape of its payload. There is no central registry.

The version is what makes a five-year-old event decodable. When a payload gains a field, or an existing field changes meaning, the version goes up and the old reader stays for the old lines. Without it, replay after a schema change is guesswork, and 0024's promise fails silently — the worst way for it to fail.

A central registry was rejected: it becomes a twelfth module and an approval step for every new fact, and the naming rule already gives the same discipline.

## Consequences

- A type is never reused for a different fact, and a published version is never edited in place. A new shape is a new version.
- A reader dispatches on the pair (type, version) and keeps every reader it must still honour.
- The module in the name is the publisher, not the subject: it says who wrote the line.
