# A signature is an Ed25519 signature over the artifact, the evidence, the definitions and the log head

Status: accepted

Each deployment holds an Ed25519 keypair; the private key lives in KMS or an HSM and never in the application. Signing produces a signature over:

`hash(artifact + evidence set + definition versions + event-log head)`

so the signature covers the audit trail, not only the file. Her identity comes from the authenticated session and is recorded in the log; the cryptography proves the document has not changed since she signed it.

A standalone verifier checks a signed document offline, on a machine with no Ramonda installed. That is the only real test of an audit claim.

A qualified e-signature provider can be attached for clients whose jurisdiction demands one; it is a plug-in, not a redesign.

## Consequences

- The artifact is frozen at SIGNED_OFF because the hash would otherwise stop matching.
- Key rotation is a recorded event, and old signatures remain verifiable against the old public key.
- The verifier is shipped as a small, dependency-light tool, because it must still run in five years.
