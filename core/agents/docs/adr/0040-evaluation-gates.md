# Four evaluations gate every change to a skill, a prompt or a tool

Status: accepted

1. **Golden case** — the two real documents: figures exact, structure matched, prose judged against a rubric.
2. **Retrieval quality** — a labelled question-and-passage set, measuring recall and ranking.
3. **Red team** — documents and pages engineered to contain instructions, verifying that the extractor treats them as data and that no tool call escapes its clearance.
4. **Regression** — every signed document becomes a test case that the system must still reproduce.

All four run in CI. A change to a skill, a prompt or a tool cannot merge unless they pass. The suite starts small — twenty to thirty cases — and grows with every signed document.

## Consequences

- Evaluation outside CI is treated as not existing.
- The regression set is the accumulating asset: it is what makes a definition library trustworthy years later.
- Red-team cases are part of the suite from the first week, because the first fetched web page is already hostile input.
