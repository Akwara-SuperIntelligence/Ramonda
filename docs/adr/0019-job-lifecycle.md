# A Job moves DRAFTED → REVIEWED → SIGNED_OFF → DELIVERED

Status: accepted

The Author moves a Job from DRAFTED to REVIEWED by submitting it. The Signer moves it from REVIEWED to SIGNED_OFF by signing. DELIVERED records that the signed document left the system. Each transition is an event with an actor and a timestamp, and the artifact freezes at SIGNED_OFF (0013).

The Signer may also return a Job from REVIEWED to DRAFTED with a note. The return creates a new version, and the returned version stays readable, so what she rejected is never overwritten.

Four states, because "reviewed" and "signed off" are different acts by different people, and delivery is the point at which the office can say the document was actually sent.

## Consequences

- A Job cannot skip REVIEWED, and the Author cannot reach SIGNED_OFF.
- DELIVERED is recorded, not inferred: export alone does not deliver.
- A return is a transition with an actor and a note, not an edit by the Signer.
