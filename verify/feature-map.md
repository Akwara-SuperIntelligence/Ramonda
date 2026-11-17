# Feature map

Nine Akwara Cafe checks from [Demo scenarios](../docs/v0.1/03-demo-company.md#demo-scenarios).

| Check | What happens | Requirements |
| --- | --- | --- |
| 1 ([ramonda check 1](ramonda)) | Amina asks why croissant waste is up at Westlands. The answer uses her branch's sales and bakery deliveries. | [R4](../docs/v0.1/02-prd.md#permissions), [R8](../docs/v0.1/02-prd.md#gateway-and-connectors) |
| 2 | David asks the same question and also sees croissant margin. | [R4](../docs/v0.1/02-prd.md#permissions) |
| 3 | Brian asks the same question and sees only his shifts. | [R4](../docs/v0.1/02-prd.md#permissions), [R5](../docs/v0.1/02-prd.md#permissions) |
| 4 | A cut to weekday croissant replenishment is proposed to Grace. Odoo is unchanged until she approves. | [R12](../docs/v0.1/02-prd.md#approvals), [R13](../docs/v0.1/02-prd.md#approvals) |
| 5 | Grace approves in the Ramonda app. Approving only on Rakazo's own card does not release the write. Ramonda's approval step is the one that counts and is audited ([requirements](../docs/v0.1/02-prd.md#approvals), [security model](../docs/v0.1/05-security-model.md#approvals)). The gateway writes Westlands 60 and Kilimani 38 into Odoo Inventory, as the person who asked. | [R8](../docs/v0.1/02-prd.md#gateway-and-connectors), [R12](../docs/v0.1/02-prd.md#approvals) |
| 6 | The audit log records the action, who asked, Grace's decision, and Odoo. The action and the event commit together in Postgres and appear on Redpanda. | [R15](../docs/v0.1/02-prd.md#audit-and-events), [R16](../docs/v0.1/02-prd.md#audit-and-events), [R17](../docs/v0.1/02-prd.md#audit-and-events) |
| 7 | An email of that approval arrives in Mailpit. If it disagrees with the log, the log wins. | [R21](../docs/v0.1/02-prd.md#email) |
| 8 | Asking, approving, and the alert happen in the Ramonda web and mobile app. WhatsApp is not used. | [R19](../docs/v0.1/02-prd.md#app-and-notifications) |
| 9 | The Monday pack matches the template and the four past packs, not the finance deck and not the excluded draft. Brian cannot open it. Grace's approval is for that version. The file lands in Nextcloud. The log records who acted, create or edit, the version, the sources, and which template and past packs were followed. A second run keeps version 1 and writes version 2, which needs its own approval. | [R22–R31](../docs/v0.1/02-prd.md#artifacts) |

Check 1 is [ramonda check 1](ramonda). The command requires Westlands butter-croissant sales of 3200 and deliveries of 3840 from 2026-09-22 through 2026-11-16, weekday deliveries of 80, weekday sales of 74 in the first five weeks and 58 in the last three, one audit row each for `odoo_pos_sales` and `odoo_bakery_deliveries` naming Amina, Brian's token returning Brian, an intact hash chain, and, when `DEEPSEEK_API_KEY` is set, a Rakazo reply that quotes the first day's sales and delivery and the last day's sales.
