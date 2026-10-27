# Authentication is an OIDC/JWKS boundary, not a vendor

The core understands exactly one thing: an OIDC token, verified against the Tenant's JWKS, issuer and audience, from which it reads Tenant, Principal, groups and Clearance. Anything else is configuration.

The default hosted broker is Stytch (free to ten thousand monthly users and five enterprise connections, which covers the first clients). Clerk is the step after that. WorkOS is avoided: it is US-hosted, and no major auth vendor has an African region, which matters more than price for a bank or an AU body.

Reason: the residency question decides the vendor, not the price. A self-hosted Keycloak or Zitadel profile ships from day one for sovereign Cells, and because the core only consumes a verified token, moving a Tenant from a broker to a self-hosted IdP is a configuration change rather than an authentication rewrite. Each Cell carries its own JWKS, which also means a client can bring their own IdP.

**Consequence:** no vendor session model, no hosted login UI, and no vendor SDK inside the core. Authorization stays in our own tables: a `tenant_id` plus Classification and Clearance filter is sufficient for the first twenty tenants, so no Zanzibar-style service in v1.
