# Two workflows on one desk: the Coordinated Positions Document and the Continental Expert Consultation Report

Status: accepted

**Workflow 1 — Coordinated Positions Document.** Built before a Codex session. One section per Agenda Item: Background, African Position, Rationale, Proposed statement, Recommendations; plus executive summary, overview tables and a signature page.

**Workflow 2 — Continental Expert Consultation Report.** Built after a continental expert meeting. Per-item positions, technical-comments tables, addenda prepared after the meeting, and follow-up actions with named leads.

Both belong to the same desk and the same Signer, and share the evidence rules, versioning and signature (0013), clearance (0004) and sources (0009). They differ in Procedure and in document structure, which is where the modular boundary sits: a workflow is a module, not a branch in shared code.

Two finished examples of these documents exist and will be ingested. The system must reproduce their structure, not approximate it.

These two are the whole list. There is no annual or multi-year roll-up: every product the desk signs is tied to one Session or one consultation, and a Job never aggregates other Jobs.

## Structural check

The documents' sections, their order, their tables and their headings are compared against the examples. A document that does not match cannot reach SIGNED_OFF. The documents win over a Procedure rule that disagrees, and the rule is corrected.

## Consequences

- Building the second workflow is the test of the modular monolith, not a second project.
- The two examples are both the golden case and the structural specification.
