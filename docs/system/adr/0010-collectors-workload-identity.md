# Collectors run on our side first, and always use workload identity

Connectors run inside the Cell and hold the Tenant's Source credentials, sealed with a per-Cell key. An edge agent that the client installs — outbound only, over mTLS — is the design target for clients that cannot let credentials or documents leave their network, and for on-premise file shares. Both shapes send the same signed envelope, so a Connector can move into the tenant without changing the core.

Reason: cloud-side Connectors have no install friction and that is how every incumbent starts; the edge agent's real value is the regulated-client conversation, and it is cheaper to keep one protocol than to rewrite the collection layer later.

A Collector authenticates to the platform as a workload — per-Tenant service identity, short-lived credentials or mTLS, scoped to the Sources it reads. It is never a person's OAuth token used as a service credential, and no shared secret is committed to a Pack.
