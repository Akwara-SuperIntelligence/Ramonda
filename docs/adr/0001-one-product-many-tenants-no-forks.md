# One product, many Tenants, no forks

Every client is served by this repository. What differs per client lives in that Tenant's Pack. We never fork the repository, never copy a module into a client variant, and never keep a branch per client.

Reason: a fork means each client's repository knows only its own security fixes, and the fifth client costs as much as the first.

**Consequence:** a difference that cannot be expressed as data is a design bug in the platform, not a client request. Fix the model for everyone and test it with the second Tenant.
