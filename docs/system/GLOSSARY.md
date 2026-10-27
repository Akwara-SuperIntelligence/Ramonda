# Ramonda — System Glossary

The platform reads an enterprise's documents and systems, assembles the work a person must finish, applies the enterprise's own written rules, and refuses to let a number through without a corroborating source. This glossary fixes the words. The decisions live in `adr/`.

## Work

**Case**:
One piece of work a person must finish, with one Subject and one or more Triggers.
_Avoid_: ticket, task, job, alert

**Trigger**:
An event that creates a Case or adds to one. An alert from a monitoring system is the usual kind.
_Avoid_: signal, event, incident

**Subject**:
The person or organisation a Case is about.
_Avoid_: customer, client, entity, party

**Decision**:
The declared outcome of a Case, taken from the outcome list in the Pack, with its reasoning and supporting Evidence.
_Avoid_: disposition, verdict, result, resolution

**Review queue**:
The ordered set of Cases that stopped and wait for a person.

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
The place a value came from: the section, the paragraph, the printed page where the document has pages, and a frozen Quote.
_Avoid_: location, pointer, coordinates, offset

**Quote**:
The exact text stored at an Anchor, so that a moved Anchor is detectable.

**Lifecycle**:
The pipeline state of a Document, from discovery to indexed or quarantined. It never carries a person's judgement.
_Avoid_: status, state

**Quarantine**:
The state of a Document that was accepted but cannot be parsed, or whose access cannot be mapped. It keeps its reason and is never dropped.

**Review decision**:
A person's signed judgement that a Document may be used by the platform. It gates use; it never gates intake.

**Picture text**:
Text read from a picture rather than from the text layer. It is Evidence about the picture, never the document's prose.

## Sources and rules

**Source**:
A system that supplies data to the platform.
_Avoid_: connector, feed, integration

**Connector**:
The code that reads one Source and hands its data to the platform.
_Avoid_: adapter, plugin

**Source class**:
A group of Sources that share one upstream, so they can fail together. A screening vendor and its reseller are one class.
_Avoid_: independence group, trust tier

**Mapping**:
The Pack's description of how a Source's fields become the platform's fields.

**Pack**:
The versioned data that makes the platform serve one use case for one client: Sources, rules, Checks, the outcome list, the report template and the vocabulary.

**Rule**:
A written instruction from the client, held in the Pack as data, that the deterministic engine evaluates against a Case.
_Avoid_: policy, logic, expression, formula

**Claim**:
A statement a Case needs to be true, such as "the total is more than 10,000". A Check compares a Claim, not a raw number.

**Check**:
A Rule that requires one Claim to be confirmed by two Sources from different Source classes.
_Avoid_: verification, corroboration, validation, cross-reference

**Discrepancy**:
A case where two Sources do not confirm the same Claim. The Case stops and a person sees both values side by side.
_Avoid_: conflict, mismatch, contradiction

**Term**:
A vocabulary value identified by its scheme and its id, never by its name alone.
_Avoid_: label, tag, category, code

**Entities**:
The typed facts a Pack attaches to a Document or a Case, validated against the Pack's schema.
_Avoid_: metadata, attributes, extra fields

## Evidence

**Evidence**:
One append-only record that ties a value to its Anchor and to the Source that confirmed it.

**Evidence ledger**:
The hash-chained, append-only sequence of Evidence and human signatures for a Cell.

**Regulator bundle**:
The export of one Case: every number, its Anchor, the Source that confirmed it, the Pack version it was judged under, and every human signature.

## Tenancy and access

**Tenant**:
The enterprise that owns a Cell.

**Cell**:
One complete deployment of the platform for one Tenant.
_Avoid_: instance, environment, installation

**Principal**:
A person or group that may see a Document.
_Avoid_: user, subject, identity

**Classification**:
The access level of a Document or a Principal.
_Avoid_: label, security level, sensitivity

**Clearance**:
The highest Classification a Principal may see.

**Workload identity**:
The identity a Connector uses to call the platform. It is never a person's token.
_Avoid_: service account, API key, shared secret
