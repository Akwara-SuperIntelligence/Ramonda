# A model call is recorded as a receipt, flushed once per Run

Status: accepted

The model transport returns the answer and a receipt for the call: the model, the hash of the input context, the output, the tool calls it made, the tokens and the time. The agent step holds its Run's receipts in memory and flushes them once, when the step ends, in the same transaction that saves the Run. The flush is a single call to shared's append carrying an opaque correlation id — the Run's id. Shared never learns what a Run is.

The transport does not write the log itself. That would put a write in the path of every model call and make drafting depend on the log being available, which is exactly the dependency 0053 removes. One local flush per Run is cheap because it happens in a transaction the step already runs.

A model call that never reaches the flush belongs to a Run that was never saved, so no Artifact can cite it (0024). A flush that fails fails the step, which is correct: a Run that cannot be recorded must not become evidence.

## Consequences

- The agent author writes no append. There is one call site per Run, in the step wrapper, not one per agent and not one per tool.
- Tool calls use the same receipt path, so a Run's model calls and tool calls are recorded together or not at all (0015).
- A crash mid-step loses that step's receipts and nothing else, because the step's state was never committed.
- The correlation id is opaque to shared. It is the one piece of the Run that crosses the boundary, and it crosses as a string.
