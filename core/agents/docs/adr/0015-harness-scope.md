# Skills, job-scoped memory and the tool registry ship; cross-session learning does not

Status: accepted

v0.1 ships Agentic Skills as on-demand Markdown SOPs, job-scoped context and memory, and a typed, permission-checked tool registry. Cross-session learning — persisting behaviour-changing patterns learned from past jobs — is deferred behind an interface.

A job must be replayable years later from its event log and pinned definition versions. Opaque memory that silently changes behaviour breaks exactly that promise.

## Consequences

- Anything the agent learns that is worth keeping becomes a reviewed, versioned definition or skill, not memory.
- Tools are registered with input/output types and clearance requirements, and invocation is event-logged.
