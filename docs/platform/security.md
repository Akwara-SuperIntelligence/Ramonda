# Security

The threat model, and the control for each threat. This is not a compliance checklist; it is the list of ways this specific product fails.

## 1. A Document instructs the model

Every Document is hostile. A scanned contract can contain white-on-white text, a hidden table row, or a sentence telling the model to skip a Check or ignore the Rules.

Controls:

- a Document never reaches a path that can change the Workflow, a Rule, a Permission, or the prompt;
- the model sees delimited, labelled content and is told that content is data, never instruction;
- every extracted value carries an Anchor, and no value reaches an Artifact without a Check;
- no tool call, no Source fetch and no escalation is derived from Document text;
- the output of `extract` is a typed field with an Anchor, not free text the next Step obeys.

**Residual risk:** a model can still be wrong about what a figure means. The Check catches a disagreement between Sources. It does not catch two Sources that are both misread the same way. That is what human sampling is for.

## 2. Cross-Tenant leakage

One database per Tenant, with `tenant_id` on every row as a second label. A query scoped to the wrong Tenant must not be able to return another Tenant's data.

Controls:

- the Tenant is read from the verified token, never from a request;
- one function builds the scope, and no repository call exists without it;
- a test asserts that every table with `tenant_id` is reachable only through that function;
- row-level security is available as a second lock and is enabled when a Tenant's review asks for it.

## 3. Connector credentials

A Connector may hold dozens of upstream credentials inside a Tenant's network.

Controls:

- credentials are sealed per Tenant, in that Tenant's own store, never in the Pack and never in the identity provider;
- one credential per Source, so revoking one Source does not stop the rest;
- a Connector has its own workload identity, scoped to the Sources it reads;
- no Person's token is ever used as a service credential;
- rotation is per Source and recorded, because upstream tokens expire on their own schedule and a single rotation event can break every Connector at once.

## 4. Model egress

A Tenant's Documents must not leave the region it chose.

Controls:

- the model port names its endpoint in the Tenant's configuration, so a Tenant can point at a local or self-hosted model;
- no vendor SDK with telemetry in the core; tracing is local and exported where the Tenant says;
- a model call sends the content the Step needs and nothing else; the Workflow, the Rules and the Permissions never leave;
- the Trace records the endpoint used, so "where did this page go" has an answer.

## 5. Over-broad access

A Person with `artifact:sign` on one Workflow must not sign another.

Controls:

- Permissions are per-Workflow where it matters: `workflow:run:<id>`, `artifact:sign:<id>`;
- a Permission is held by a Role, and a Role belongs to one Tenant;
- there is no implicit admin path in code;
- the API checks one Permission per request, and the UI hiding a control is never the control.

## 6. Tampering with Evidence

Controls:

- `evidence` is append-only; the application role has no `UPDATE` and no `DELETE`;
- every row carries the hash of its payload and the previous row's hash, per Tenant;
- a checkpoint is signed periodically, so a rewritten chain is detectable;
- a correction is a new row that supersedes an old one, never an edit.

## 7. A Run that quietly succeeds with wrong numbers

The dangerous failure is not an error. It is an Artifact that looks finished.

Controls:

- a figure with no Check cannot enter an Artifact;
- a Check with no Sources is `missing`, not `confirmed`;
- a Discrepancy stops the Run;
- the Artifact lists which figures were confirmed and by which Source;
- a Person signs a specific version, never "the document".

## 8. The dependency chain

A bank will scan this.

Controls:

- a small dependency set, pinned with hashes;
- no broker, no search cluster, no vendor SDK in the request path;
- a licence check in CI, because the point of a bank scan is that it happens once, before you need it.

## What is deliberately not in v0.1

- no content redaction or DLP;
- no field-level encryption;
- no customer-managed keys;
- no SSO beyond OIDC.

Each is a real request from a real review. None of them changes the shape of the system, so none of them is built before a Tenant asks.
