# Starting point: LLM apps, not agents

The learner has built LLM applications but has not built a tool-calling agent loop or any long-running job infrastructure (self-reported, session 1). This sets the floor for the course: the raw loop must be taught explicitly before any framework, and durability vocabulary (queue vs workflow, replay, idempotency) cannot be assumed. It also justifies the order: feel the loop die first, then reach for pydantic-ai or Temporal once the problem they solve is concrete.

**Implications:** do not open with frameworks; keep build steps runnable in one file; introduce Temporal only after the crash demo has landed.
