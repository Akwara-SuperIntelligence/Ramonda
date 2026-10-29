# Modules talk by synchronous read calls and asynchronous events

Status: accepted

A module may call another module's public API synchronously to read, and receives a snapshot — never another module's entities. Anything that changes state in two modules is an event. The caller does not wait for the listener and does not know who listens.

Writing into another module's schema is forbidden outright. If module A needs to write into module B's tables, the boundary is already broken and the fix is to move the boundary, not to add a helper.

## Consequences

- Read paths stay simple and debuggable; write paths stay decoupled.
- Every event that matters is also a fact in the event log (0031), so decoupling does not cost auditability.
