# Agent topology is per-workflow configuration: one router, many specialists

Status: accepted

The agent layer runs a router and a set of specialists. Which specialists exist, what each may do, which tools it holds, what context it receives and who hands off to whom is declared by the workflow in the client's configuration. It is not hardcoded in the core.

The router sends work to specialists, and independent work runs in parallel. Speed is a first-class requirement: a forty-item document is forty independent units of work, and they must not run one after another.

Specialisation is real work, not decoration. A specialist has a narrow job, a narrow tool set and a narrow context, which is also what makes it fast and cheap.

Every specialist run is logged with its input context hash, its output and its tool calls (0024). Every output is a Suggestion until a person accepts it (0013). Deterministic verification stays outside the agents entirely: the structural, citation and completeness checks are code and they gate SIGNED_OFF.

## Consequences

- A new client or a new workflow supplies a topology; it does not change the agent framework.
- The router is the only component that decides who runs, and its decisions are recorded.
- Adding a specialist is configuration plus a skill; adding a tool is core work.
