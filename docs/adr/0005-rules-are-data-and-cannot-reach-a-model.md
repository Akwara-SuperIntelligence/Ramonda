# Rules are data and cannot reach a model

A Rule is YAML in the Pack: typed operators, no loops, no recursion, no user-defined functions. Only the `harness` module holds a model client. `rules` cannot import it.

Reason: "the company's own written rules, exactly as defined" is a legal claim. A compliance officer must be able to read a Rule, sign it, and see later the exact Rule version that produced an Artifact. A rule that has to be executed to be understood cannot be signed.

**Consequence:** any behaviour that needs judgement belongs in `extract` or `draft`, and its output must carry an Anchor and pass a Check before it can reach an Artifact.
