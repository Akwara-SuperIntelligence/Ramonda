# State and its event commit together, and a relay carries the event to the log

Status: accepted

Every module owns an outbox table in its own schema, with a shape shared defines. A change of state and the event that describes it are written in the same transaction, so both commit or neither does. A relay then moves outbox rows into `events`. The log is written only by shared, with shared's own database role; no module's role ever writes into another schema.

Each module's relay reads its own outbox through that module's own connection and hands the rows to shared's append. Shared returns the log sequence, and the module marks its rows sent in its own transaction. A crash between the append and the mark sends a row twice; the event id is unique in the log, so the second copy is refused and the module marks the row sent. Delivery is at-least-once, and the log is idempotent.

Relay loops live in the worker container (0043), one per module, all supervised. A failing loop delays only its own module's events, and nothing in the request path waits for the log.

The two simplifications were considered and refused. One relay with read access to every module's schema would make a single role the largest permission in the deployment and would force shared to know every module's tables, which 0051 forbids. Appending inside the caller's transaction with a cross-schema insert would give every module write access to the log, and that permission would spread with the number of modules.

## Consequences

- 0031's append path is amended: a module does not call append, its relay does.
- The log's order is relay order, not commit order. The envelope must therefore carry the time the fact occurred; the sequence says when it reached the log, and both are needed to read history correctly.
- A module's outbox belongs to that module's schema: its migrations, its retention, its rows.
- The duplicate path is a normal case, not an error: a relay retry after a crash is expected, and the log refuses the copy by event id.
