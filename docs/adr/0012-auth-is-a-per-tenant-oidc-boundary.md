# Authentication is a per-Tenant OIDC boundary

The core understands one thing: a verified OIDC token carrying Tenant, Person, Roles and Clearance. Anything else is configuration.

Default is a cell-local Keycloak, with the customer's own IdP brokered in where they have one, and a break-glass local admin so the system stays operable when their IdP breaks. A managed broker is allowed only where the Tenant accepts processing outside its region; the US-only brokers were rejected on residency, not on price.

Connectors use a workload identity, one per Connector, never a Person's token. Upstream credentials live in the Tenant's own sealed store, never in the Pack and never in the identity provider.

**Consequence:** no vendor SDK in the core, a JWKS per Tenant, and moving a Tenant to a different IdP is a configuration change.
