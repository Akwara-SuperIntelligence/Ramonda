# The object graph starts with fourteen objects and grows by addition

Status: accepted

v0.1's graph holds fourteen objects — Session, Committee, Agenda Item, Step, Working Document, Circular Letter, Standard, Member State, Designated Lead, African Position, Technical Comment, Proposed Statement, Recommendation, Signer — and nine links: a Committee holds Sessions; a Session has Agenda Items; an Agenda Item sits at a Step; a Working Document supports an Agenda Item; a Circular Letter requests Technical Comments; a Standard is discussed under an Agenda Item; a Member State has a Designated Lead; a Person holds an African Position on an Agenda Item; a Job covers a Session.

The set is not a specification of the domain; it is the smallest set the first document needs. Missing objects are discovered by building the document, not by modelling in advance, and are added as they appear.

## Consequences

- Adding an object or a link is a migration plus a permission declaration, never a redesign of queries. Anything that requires a redesign is evidence the graph was wrong, not that the domain was large.
- Member State is data, not a clearance dimension: both users see every object in v0.1, and no state-level visibility rule exists.
- The graph is versioned, so a document can always be read against the graph it was produced with.
