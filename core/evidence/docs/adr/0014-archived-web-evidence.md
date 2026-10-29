# No figure ships unless the passage it came from was archived at fetch time

Status: accepted

Web evidence is fetched by a separate fetch service that archives each page to object storage with URL, retrieval timestamp and content hash, then extracts candidate figures into structured records. The agent sees those records, never the raw page, and page content is treated as data throughout — never as instructions. Citations are generated from the archived snapshot and its exact quote.

A fetched page is hostile input: it can contain text engineered to be read as instructions. Snapshotting also answers the question a delegate or auditor will ask — what exactly did the source say on the day the document was made?

## Consequences

- The artifact can cite only from stored snapshots.
- The candidate log is part of the evidence set, so "what did you search and reject" is answerable.
- Prompt-injection defences are structural, not a prompt instruction.
