# Ramonda — Codex Coordination

The vocabulary of the African Union's Codex coordination desk and of the system that produces its signed work products.

## Language

### Codex proceedings

**Session**:
A single sitting of the Codex Alimentarius Commission or of one of its committees, identified by a session code such as `SESSION_X` and never fixed in the system in advance.
_Avoid_: Meeting, round, sitting

**Codex Committee**:
A subsidiary body of the Commission that elaborates standards within a subject area or region, such as CCAFRICA.
_Avoid_: Working group, panel

**Agenda Item**:
A numbered matter for decision or discussion at a session, carrying its own documents, positions and outcome.
_Avoid_: Topic, point, agenda line

**Step**:
A stage in the eight-step procedure by which a Codex text is elaborated, cited as `Step 5`, `Step 8`, or the accelerated `5/8` shorthand that skips Steps 6 and 7.
_Avoid_: Phase, stage, round

**Session Report**:
The official record of a session's decisions and discussion, cited by a `REP` code such as `REP26/AFRICA`.
_Avoid_: Minutes, proceedings, summary

**Circular Letter**:
A formal request from the Secretariat to member states for comments by a stated deadline, cited by a `CL` code.
_Avoid_: Call for comments, consultation, survey

**Working Document**:
A paper prepared for a session's consideration, such as a project document, discussion paper or agenda-item paper.
_Avoid_: Input file, source file, attachment

**Standard Text**:
The adopted Codex instrument under discussion, whether a standard (`CXS`), guideline (`CXG`) or code of practice (`CXC`).
_Avoid_: Regulation, rule, spec

**Procedure**:
The versioned encoding of how a body moves an item through the steps and what a given session must produce, ending at the signed Coordinated Positions Document.
_Avoid_: Workflow, pipeline, process, template

**Addendum**:
A signed addition to a document issued after its signature, carrying its own version and its own signature.
_Avoid_: Appendix, annex, update

### The desk

**Desk**:
The customer's office for which a job is run — in v0.1, exactly two people, the Author and the Signer.
_Avoid_: Team, client org, department

**Author**:
The person who drafts a job's artifact and is answerable for its content.
_Avoid_: Drafter, writer, editor, analyst

**Member State**:
An African Union member state represented at a session and holding a national position.
_Avoid_: Country, delegation, member

**Designated Lead**:
The person accountable for a member state's or the desk's input on one agenda item.
_Avoid_: Owner, focal point, contact

**African Position**:
The common position the desk advances on an agenda item on behalf of the region.
_Avoid_: Common position, regional view

**Technical Comment**:
A formal comment submitted on a draft text, addressed to specific provisions and steps.
_Avoid_: Feedback, remark, edit

**Proposed Statement**:
The exact wording the desk proposes be adopted or recorded on an agenda item.
_Avoid_: Draft text, wording proposal

**Recommendation**:
A proposed action for the region or for member states arising from an agenda item.
_Avoid_: Action item, next step

**Regional Follow-up**:
An action assigned to a named lead after a session, with a due point in the Codex calendar.
_Avoid_: TODO, action

**Coordinated Positions Document**:
The signed, audit-ready document stating the region's positions for one session, item by item.
_Avoid_: Brief, pack, paper, dossier

**Continental Expert Consultation Report**:
The signed record of a continental expert meeting, covering item positions, technical comments, addenda and follow-ups.
_Avoid_: Workshop report, consultation summary

**Signer**:
The named official — the Head of the AU Nairobi office or the CCAFRICA Coordinator — whose signature releases a document.
_Avoid_: Approver, authoriser, reviewer

### Ramonda

**Listener**:
A standing connection to one enterprise data source that captures new and changed material without being asked.
_Avoid_: Crawler, poller, sync job

**Source Adapter**:
The code that translates one source's native format into Ramonda's normalized document and record contracts.
_Avoid_: Connector, plugin, integration

**Typed Object Graph**:
The client's business modelled as typed entities and typed relationships — companies, facilities, covenants or sessions, agenda items, standards — against which every figure is interpreted.
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

**Artifact**:
The finished work product the system delivers for a job — a Coordinated Positions Document, a spreadsheet, a slide deck.
_Avoid_: Output, deliverable, document

**Interaction Mode**:
The state that decides how a person's actions affect an artifact — Editing, Suggesting or Viewing.
_Avoid_: Edit mode, view mode, permission

**Suggestion**:
A proposed change that does not alter the artifact until a person accepts it; accepting it creates a version.
_Avoid_: Comment, edit request, change

**Artifact Version**:
One immutable snapshot of an artifact, created by every edit, applied suggestion or chat instruction.
_Avoid_: Revision, draft, save

**Clearance**:
The set of entities, sources and actions a person's position entitles them to see or take, inherited unchanged by any agent acting for them.
_Avoid_: Permission, role, access level

**Job**:
One unit of work the desk hands over — one session's Coordinated Positions Document, one consultation report — with its own state, evidence and sign-off.
_Avoid_: Case, ticket, task, project

**Run**:
One execution of the agent on a job, with its own input, tool calls and output.
_Avoid_: Task, invocation, cycle
