# REST with OpenAPI, server-sent events for streaming, webhooks for delivery

Status: accepted

The client application talks to a REST API described by OpenAPI, with a generated TypeScript client. Sections and chat tokens stream over server-sent events. Delivery events are webhooks.

The API is a small number of resource operations — job, artifact, suggestion, search, chat — and the generated client is what keeps one repository (0025) honest: a breaking change is a build failure.

## Consequences

- The OpenAPI spec is a deliverable; the generated client is never hand-edited.
- Streaming is required by the performance budget (0037): waiting for a whole document before showing anything fails it.
- Webhooks are signed with the deployment key so a receiver can verify them.
