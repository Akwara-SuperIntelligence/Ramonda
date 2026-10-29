# Five agent roles, instantiated by each workflow

Status: accepted

The roles are functions, not one document's sections:

| Role | Job | Runs |
|---|---|---|
| Scout | finds material, fetches it, archives it, extracts candidate claims and figures | per item, parallel |
| Analyst | reads evidence and prior positions, decides the stance and its reasoning | per item, parallel |
| Drafter | writes prose into the Structure Spec, within the style rules | per item, parallel |
| Verifier | runs the deterministic checks and reports — code, not an agent | per section, as it lands |
| Editor | reads the document digest and removes contradiction and duplication | once per document |

Each workflow supplies its own sections, skills, specialist set and context rules; the roles themselves are shared. The first workflow's five roles map onto its five sections. The second workflow uses the same roles with different skills, a different Structure Spec and a technical-comments table instead of a prose section.

## Consequences

- A new workflow is configuration and skills, not a new agent framework.
- A specialist's context is assembled by code from the job's state (0036), never from a chat transcript.
- Adding a sixth role is a deliberate act with a named job, not a way to route around a weak skill.
