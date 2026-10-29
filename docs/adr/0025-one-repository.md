# One repository, two deployables

Status: accepted

The backend and the first-party client application live in the same repository and are built and deployed separately, sharing generated API types. The artifact editor and the backend's versioning rules are too tightly coupled to negotiate across a repository boundary at this stage.

## Consequences

- The API contract is generated from the backend and consumed by the client, so a breaking change is a build failure rather than a runtime surprise.
- Splitting the repository later is mechanical; merging two repositories is not.
