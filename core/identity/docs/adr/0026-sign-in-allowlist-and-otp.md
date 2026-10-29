# Sign-in is an allowlist of specific email addresses plus a one-time passcode

Status: accepted

v0.1 authenticates with a one-time passcode sent to an email address, and only addresses on an explicit allowlist are accepted. There is no organisation directory to authenticate against yet, and no SSO. Any other address is rejected.

The allowlist is data, not code: adding the client's second user is an entry, not a deployment.

## Consequences

- The identity module owns the allowlist and must be able to attach a client directory later without changing `jobs` or `artifacts`.
- There is no self-service signup, and none should exist: every account is intentional.
