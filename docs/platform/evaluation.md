# Evaluation

Four questions decide whether a Run is any good. Each has a measurement, and each measurement has a place it runs.

## 1. Did it find the right pages?

**Retrieval hit rate** on a labelled set: for a known question, did the Chunk that holds the answer appear in the top *k* returned by `retrieve`?

Measured per Tenant, because a Tenant's vocabulary is its own. A hit rate without a labelled set is a feeling.

Where: a labelled file of `(question, expected document_version, expected Anchor)`, replayed on every Pack change.

## 2. Did it extract the right value?

**Field accuracy**, per field, never averaged into one number. `budget_spent` at 97% and `budget_released` at 61% is not 79% of anything; it is one field you cannot ship.

Every extracted value must carry an Anchor, so a wrong value is checkable by a Person in one click. An extraction with no Anchor counts as wrong even when the number is right.

Where: the same labelled set, scored on `extract` alone with a fake model call replayed from fixtures.

## 3. Did it catch the disagreement?

This is the one that matters, and it has two error directions with different costs.

| Error | What happens | Cost |
|---|---|---|
| **Missed Discrepancy** | two Sources disagree, the Run drafts anyway | a wrong figure reaches an Artifact that looks finished. This is the failure the product exists to prevent |
| **False Discrepancy** | two Sources agree, the Run stops | a Person spends ten minutes. Annoying, not dangerous |

**Gate: zero missed Discrepancies on the labelled set.** Not 99%. Zero. Precision is tuned afterwards, because a false stop costs minutes and a missed stop costs the claim on the whole product.

Where: fixtures with a deliberate disagreement, plus a labelled set of real disagreements from the Tenant.

## 4. Is it affordable?

Per Run: tokens, model cost, wall time, and how much of it a Person waited for.

A perfect answer at 40 seconds and a high cost is not a product. The budget per Run is set with the Tenant and recorded in the Pack's manifest, so a Pack that doubles the cost is visible before it installs.

## The gates

| Gate | When | Pass condition |
|---|---|---|
| Pack fixtures | every install | every fixture matches its expected outcome, including one deliberate stop |
| Labelled retrieval set | before a Tenant goes live | hit rate agreed with the Tenant on their own documents |
| Discrepancy recall | every Pack change | zero missed on the labelled set |
| Cost and latency | every release | inside the Pack's declared budget |
| Human sampling | every week a Tenant is live | 10% of signed Artifacts re-read by a second Person |

## Why human sampling stays

The Checks catch a disagreement between Sources. Nothing catches two Sources that are both wrong in the same way, and nothing catches a Rule that the Tenant wrote badly.

Sampling is how the system finds out that a Tenant's Rule is wrong, and it is the only input that improves the Rules rather than the code. The finding goes back into the Pack, never into a code change.

## What evaluation is not

It is not an LLM judge scoring prose. A judge model grading another model's writing measures style, and this product is not judged on style.

It is not a benchmark. MMLU and its relatives measure a model, not a Run.
