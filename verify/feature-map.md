# Feature map

This file is the safety net for the plumbing in slices 0 and 1. It is not the product test. Stages are scored against the simulator's hidden record, as in [the build plan](../docs/v0.1/08-build-plan.md#how-a-stage-counts-as-done). [Decision 19](../docs/v0.1/07-decisions.md#19-build-the-map-from-the-systems-and-test-with-the-simulator) withdrew the other eight scripted checks. Do not add them back. Do not add planted facts.

## Check 1

[ramonda check 1](ramonda) is `verify/ramonda check 1`. It needs the local stamp from the [README](../README.md) and a run of `scripts/seed_akwara_cafe.py`.

The command loads that seed module and checks Odoo against the module's own days, for the branch and product named in the module. It does not keep a second copy of the figures. Do not copy those figures into a new test.

It also requires all of the following.

- The new audit rows are `odoo_pos_sales` and `odoo_bakery_deliveries`, in that order, and the actor is the user `amina`.
- A token for the user `brian` returns `brian`, including when the tool arguments name someone else.
- The hash chain of the audit log is intact.
- When `DEEPSEEK_API_KEY` is set, Rakazo quotes the first day's sales and delivery and the last day's sales from that same seed. When the variable is unset, the command skips that part.

`amina` and `brian` are fixtures of this command and of the local Keycloak realm. They are not the cafe's org chart. Do not add named people to satisfy a new check.

A green result does not pass a product stage.
