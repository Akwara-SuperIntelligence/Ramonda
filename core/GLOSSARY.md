# Ramonda

The platform vocabulary, shared by every client. For the first client's domain language, see [AU Codex](../clients/au_codex/docs/GLOSSARY.md).

## Language

### Work and roles

**Desk**:
The customer's office for which a job is run.
_Avoid_: Team, client org, department

**Author**:
The person who drafts a job's artifact and is answerable for its content.
_Avoid_: Drafter, writer, editor, analyst

**Signer**:
The named official whose signature releases a document.
_Avoid_: Approver, authoriser, reviewer

**Job**:
One unit of work the desk hands over, with its own state, evidence and sign-off.
_Avoid_: Case, ticket, task, project

**Run**:
One execution of the agent on a job, with its own input, tool calls and output.
_Avoid_: Task, invocation, cycle

**Procedure**:
The versioned encoding of how a body moves a work item through its stages and what a given deliverable must contain, ending at the signed artifact.
_Avoid_: Workflow, pipeline, process, template

**Addendum**:
A signed addition to a document issued after its signature, carrying its own version and its own signature.
_Avoid_: Appendix, annex, update

**Artifact**:
The finished work product the system delivers for a job — a document, a spreadsheet, a slide deck.
_Avoid_: Output, deliverable, document

**Artifact Version**:
One immutable snapshot of an artifact, created by every edit, applied suggestion or chat instruction.
_Avoid_: Revision, draft, save

**Interaction Mode**:
The state that decides how a person's actions affect an artifact — Editing, Suggesting or Viewing.
_Avoid_: Edit mode, view mode, permission

**Suggestion**:
A proposed change that does not alter the artifact until a person accepts it; accepting it creates a version.
_Avoid_: Comment, edit request, change

**Clearance**:
The set of entities, sources and actions a person's position entitles them to see or take, inherited unchanged by any agent acting for them.
_Avoid_: Permission, role, access level

### Knowledge and evidence

**Listener**:
A standing connection to one enterprise data source that captures new and changed material without being asked.
_Avoid_: Crawler, poller, sync job

**Source Adapter**:
The code that translates one source's native format into Ramonda's normalized document and record contracts.
_Avoid_: Connector, plugin, integration

**Typed Object Graph**:
The client's business modelled as typed entities and typed relationships, against which every figure is interpreted.
_Avoid_: Knowledge graph, ontology, data model

**Definition**:
A versioned, purely functional encoding of one of the client's written rules, which computes a result from stated inputs and nothing else.
_Avoid_: Rule, formula, calculation, prompt

**Holding Area**:
Where an extracted value waits until its provenance and corroboration are settled, before it can enter the Typed Object Graph.
_Avoid_: Staging, inbox, queue

**Corroboration**:
A declaration that two named sources are independent for a specific figure, making agreement between them meaningful.
_Avoid_: Validation, cross-check, verification

**Promotion**:
The act of admitting a held value into the Typed Object Graph, either silently on corroboration or explicitly by a named person.
_Avoid_: Ingest, commit, accept

**Exception Queue**:
The surface where conflicting or single-source values are shown side by side for a human to resolve.
_Avoid_: Error log, review queue, triage

**Figure**:
A number, date or citation asserted in an artifact, each of which traces to one Calculation or Evidence record.
_Avoid_: Statistic, data point, value

**Calculation**:
One execution of a Definition on stated inputs, recorded with the rule version and the result so any Figure can be explained.
_Avoid_: Formula, computation job, run

**Provenance**:
The source, exact location and retrieval moment of a value, kept so every figure can be traced to a page.
_Avoid_: Metadata, source info, attribution

**Source Candidate**:
One of the options the agent found while searching for a figure, recorded with the reason it was chosen or rejected.
_Avoid_: Search result, hit, alternative

**Disclosure**:
The explicit statement in an artifact that a figure rests on a single source, with what was searched and what was rejected.
_Avoid_: Caveat, footnote, disclaimer
