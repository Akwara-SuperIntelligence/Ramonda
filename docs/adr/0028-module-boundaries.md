# Module boundaries follow change, not concepts

Status: accepted

The test for a boundary is simple: can the inside of this module change without forcing a change in another module? Two things that always change together are one module. Two things that change for different reasons are two modules, even if they sound related.

Settled splits:

- **Identity is not Access.** Identity answers "who are you". Access answers "what may you see". Adding a sign-in method changes Identity and nothing else; adding a visibility rule changes Access and nothing else.
- **Sources is not Ingestion.** Sources connects to the outside world and notices that something new exists. Ingestion turns what arrived into usable text. A new connector changes Sources; a new PDF layout changes Ingestion.
- **Ingestion is not Search.** Ingestion makes text findable. Search finds it. A new parser changes Ingestion; a new ranking model changes Search.
- **Definitions is not Ontology.** Ontology is the nouns — the enterprise's objects and links. Definitions are the rules that compute over them. A new rule changes Definitions; a new object type changes Ontology.
- **Evidence is not the job.** Evidence is proof: what a source said, when, and where. The work unit is the job's state and lifecycle. A new citation rule changes Evidence; a new approval state changes the job.

**Artifacts is backend only.** The document model, its versions, suggestions and export are backend. The editor the user sees is the client application, not a module. They are not in the same code.

## Consequences

- A module name is plain language, not jargon: no "corpus", no invented words.
- A change that forces edits in two modules means the boundary is wrong. Refactor the boundary before adding the feature.
- Cross-module calls go through the public API and receive snapshots, never another module's entities.
