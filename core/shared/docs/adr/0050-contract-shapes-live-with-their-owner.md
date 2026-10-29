# Contract shapes live with the module that owns the data

Status: accepted

0047 says core supplies the normalized document and record shapes, the Source Adapter and Definition interfaces, the Structure Spec format, and the Calculation and Evidence record shapes. It does not say which package holds them. They stay with the module that owns the data: the normalized document in `ingestion`, `Definition` and the Calculation Record in `definitions`, the Source Adapter in `sources`, the Structure Spec in `artifacts`, the Evidence Record and its candidate log in `evidence`.

A shape is part of the contract of the module whose rows it describes. Moving the shapes into shared would make shared know what a document, a rule or an evidence record is, which 0049 forbids. It would also recreate one type package whose only rule is that it is not somewhere else.

The single exception is the event envelope, which shared owns because the event log is shared (0031). An event is not a module's entity; it is a fact about the log itself.

## Consequences

- A caller gets another module's shape by importing that module's public API, and it receives a snapshot, never an entity (0030).
- A shape that two modules appear to need is evidence that the boundary is misplaced, not a reason to promote the shape into shared (0028).
- Shared stays domain-free, and that is what makes it publishable as a library.
