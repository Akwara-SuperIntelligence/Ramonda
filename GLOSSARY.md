# Ramonda v0.1

One product that runs an enterprise's own document workflows, applies the enterprise's written rules, and will not let a figure through unless a second source confirms it. This glossary fixes the words. Decisions live in `docs/platform/`.

## The organisation

**Tenant**:
One enterprise: the organisation that owns this system and its data. AU is one; an insurance company is one.
_Avoid_: client, customer, account, workspace, org, cell

**Person**:
Someone who signs in, inside exactly one Tenant.
_Avoid_: user, principal, member, actor, identity

**Role**:
A named set of Permissions inside one Tenant, such as CFO or Intern.
_Avoid_: group, team, tier, level

**Permission**:
One right a Role carries: running a named Workflow, signing an Artifact, reading a Document at a Classification, exporting Evidence.
_Avoid_: scope, grant, capability, privilege

## Work

**Workflow**:
One repeatable process that belongs to exactly one Tenant and is described as data in that Tenant's Pack.
_Avoid_: pipeline, flow, job, bot, agent, cell, process

**Step**:
One entry in a Workflow: one verb, its inputs, and the output it must produce.
_Avoid_: node, task, action, activity

**Verb**:
One operation the engine can perform on a Workflow's behalf. There are seven, and only the platform adds more.
_Avoid_: tool, function, action, capability

**Run**:
One execution of one Workflow over one Subject at one time, bounded in steps and in time.
_Avoid_: job, execution, instance, case, session

**Subject**:
The thing a Run is about: a member state, a claim, a department.
_Avoid_: entity, record, item, target

**Artifact**:
What a Run produces: a draft a Person can read, correct and sign. It has versions.
_Avoid_: output, deliverable, report, document

**Signature**:
A Person's recorded act of accepting one Artifact version.
_Avoid_: approval, sign-off, decision, disposition

**Pack**:
All the data for one Tenant: its Workflows, Sources, Rules, Checks, vocabulary and templates. A Pack contains no executable code.
_Avoid_: config, bundle, plugin, module, package

## Documents

**Document**:
A unit of identity, version, provenance and access, received from a Source.
_Avoid_: file, asset, attachment

**Document version**:
One immutable content state of a Document, identified by its content hash. A citation names a version, never a Document.
_Avoid_: revision, copy

**Block**:
One structural unit of a Document: a heading, a paragraph, a list item, a table, or a figure.
_Avoid_: element, node, segment

**Chunk**:
A retrievable piece of one Document version, with exactly one Anchor.
_Avoid_: passage, excerpt, fragment

**Anchor**:
The place a value came from: the section, the paragraph, the printed page where the Document has pages, and a frozen Quote.
_Avoid_: location, pointer, coordinates, offset

**Quote**:
The exact text stored at an Anchor, so that a moved Anchor is detectable.

**Quarantine**:
The state of a Document that was accepted but cannot be parsed, or whose access cannot be mapped. It keeps its reason and is never dropped.

**Picture text**:
Text read from a picture rather than from the text layer. It is Evidence about the picture, never the Document's prose.

## Sources

**Source**:
A system that supplies data to the platform.
_Avoid_: connector, feed, integration

**Connector**:
The code that reads one Source and hands its data to the platform.
_Avoid_: adapter, plugin, driver

**Source class**:
A group of Sources that share one upstream, so they can fail together. Two Sources in one class never confirm each other.
_Avoid_: independence group, trust tier

**Mapping**:
The Pack's description of how a Source's fields become the platform's fields.

## Rules

**Rule**:
A written instruction from the Tenant, held in the Pack as data, that the engine evaluates against a Run.
_Avoid_: policy, logic, formula, expression

**Claim**:
A statement a Run needs to be true, such as "the total is more than 10,000".
_Avoid_: assertion, fact, condition

**Check**:
A Rule that requires one Claim to be confirmed by two Sources from different Source classes.
_Avoid_: verification, validation, corroboration

**Discrepancy**:
The state where two Sources do not confirm the same Claim. The Run stops and a Person sees both values side by side.
_Avoid_: conflict, mismatch, contradiction

**Term**:
A vocabulary value identified by its scheme and its id, never by its name alone.
_Avoid_: label, tag, category, code

**Entities**:
The typed facts a Pack attaches to a Document or a Run, validated against that Pack's schema.
_Avoid_: metadata, attributes, extra fields

## Evidence and observation

**Evidence**:
One append-only record that ties a value to its Anchor and to the Source that confirmed it.

**Evidence ledger**:
The hash-chained, append-only sequence of Evidence and Signatures for one Tenant.

**Trace**:
The operational record of one Run: every model call, every verb, every retrieval, with tokens, cost and time. It expires.

**Explain**:
The page a Person reads to answer "why does this figure say 41": the value, its Anchor, the two Sources, the Rule version, and a link to the Trace.

## Access

**Classification**:
The access level of a Document, or of a Person's Clearance.
_Avoid_: label, security level, sensitivity

**Clearance**:
The highest Classification a Person may see.

**Workload identity**:
The identity a Connector uses to call the platform. It is never a Person's token.
_Avoid_: service account, API key, shared secret

## The build

**Module**:
One of six parts of the codebase, each with one reason to change and a public interface: `documents`, `harness`, `rules`, `work`, `evidence`, `access`.
_Avoid_: crate, package, service, component, microservice
