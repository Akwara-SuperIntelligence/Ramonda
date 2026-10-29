# Sources for v0.1: the Codex document API and one Google Drive folder

Status: accepted

The Listener attaches to two sources: the Codex Alimentarius document REST API, and one Google Drive folder belonging to one of the two users. No mailbox, no Slack, no SharePoint in v0.1.

Two adapters prove the Source Adapter contract without building a plugin framework, and they cover both the authoritative public record and the desk's own working material.

## Consequences

- Anything living in email or chat is out of scope, and the document must not depend on it.
