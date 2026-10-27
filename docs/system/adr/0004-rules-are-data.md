# Rules are data, and cannot reach a model

A Rule is a YAML document in the Pack: typed operators, no loops, no recursion, no user-defined functions. It may call only a small approved list of compiled functions (`fx.convert`, `window.sum`). No module except `agent` may name a model provider, and `scripts/check-boundaries.sh` fails the build if one does, so the deterministic engine cannot physically reach a language model.

Reason: "the company's own written rules, exactly as defined" is a legal claim. A compliance officer must be able to read a Rule, sign it, and see six months later the exact Rule version that produced a Decision. A script language is Turing-complete, so termination and reachability cannot be proven before it runs, and a rule that must be executed to be understood cannot be signed. Compiled Rust per rule would be provable but every change becomes a release and the client cannot read it.

Every evaluation writes `rule_evaluation` with the rule id, the Pack version, the inputs hash and the outcome, so a Decision is replayable.
