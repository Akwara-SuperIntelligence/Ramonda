# Always-on agents — glossary

The canonical vocabulary for this course. Terms are added only once they have been used correctly in a lesson or a build step.

## The loop

**Agent**:
An LLM that autonomously chooses tools in a loop until a task is done, rather than following a code path a developer fixed in advance.
_Avoid_: bot (use for the product surface, not the mechanism), workflow

**Harness**:
The code around the model that assembles context, exposes tools, executes tool calls, and decides when to stop.
_Avoid_: framework, runtime

**Agent loop**:
The repeating three-step cycle: the model picks a tool, the harness executes it, the result is appended to context, repeat.
_Avoid_: agentic loop, ReAct loop

**Turn**:
One user-visible exchange, from an incoming message or trigger to the agent's next reply or deliberate silence.
_Avoid_: step, iteration

**Tool call**:
A structured request from the model naming a tool and its arguments, which the harness — not the model — executes.
_Avoid_: function call (unless naming the API field), action

## State and survival

**Execution state**:
Where a run currently is: the messages so far, the pending tool call, the step counter.
_Avoid_: context (that is only the part sent to the model), memory

**Durable execution**:
A run model where progress is journaled, so a retry after a crash resumes at the last completed step instead of replaying from the start.
_Avoid_: checkpointing (a weaker, related idea), retries

**Always-on agent**:
An agent whose process, state, and wake-up path live outside your terminal, so it can act while you are gone and resume after a restart.
_Avoid_: autonomous agent, background agent
