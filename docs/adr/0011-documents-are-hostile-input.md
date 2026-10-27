# Documents are hostile input

Every Document is untrusted. It can contain hidden text, white-on-white instructions, a prompt injection in a table cell, or a sentence designed to make the model skip a Check.

Controls, in order of importance:

1. A Document never reaches a path that can change the Workflow, the Rules, the Permissions or the prompt.
2. The model only ever sees delimited, labelled content, and is told that content is data.
3. Every extracted value carries an Anchor, and no value reaches an Artifact without a Check.
4. No tool call, no Source fetch and no escalation is derived from Document text.
5. A Document may produce a Discrepancy, never an exception to the Checks.

**Consequence:** features that let a model decide what to do next are out of scope, permanently.
