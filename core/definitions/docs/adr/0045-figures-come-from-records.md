# Every figure comes from a tool call, and every figure is checked against its record

Status: accepted

The model never computes. It calls `definitions.run`, which executes a versioned rule in the sandbox and returns a **Calculation Record**: the rule and its content hash, the inputs, the output and the time. Dates, counts, percentages, citation strings and table values all arrive this way.

The model writes the value in ordinary prose and returns, with each suggestion, a figures list:

```
figures: [ {value: "38%", record: "calc_7f3a"} ]
```

Code then reads every number in the finished text. Each number must appear in the list, and each entry must resolve to a real Calculation or Evidence record whose value matches the text. A number with no record, or a value that differs from its record, rejects the suggestion before a human ever sees it; the model is told why and tries again.

There are no markers in the artifact. Prose stays prose at any length, and the audit trail is a record of a calculation rather than a record of a substitution.

The same mechanism carries spreadsheets. A cell holds a formula, the formula is a Definition instance, and its Calculation Record makes the cell explainable: what rule, what inputs, what result. A human can open any cell and see its working.

## Consequences

- The residual risk is transcription, not arithmetic: a tool returns 3.8 and the model writes 38. The value comparison catches it, which is why presence of a record is not enough.
- Verification is one cheap pass of code over the text, which is affordable at a hundred pages.
- Every figure in a signed document is traceable to a rule version and an input set, years later.
- A definition used by a spreadsheet, a document and a chat answer produces the same record type, so provenance is uniform across artifact formats.
