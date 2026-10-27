# Identity & workload auth for a per-cell B2B product (2025–2026 facts)

Researched 2026-10-27 against vendor pricing pages, docs, and DPAs. Scope: one self-contained
"cell" per enterprise customer, often in a bank/government cloud or on-prem, East/West Africa and
Europe. Two identities: (1) employees via OIDC, (2) machine collectors pulling from ~50 upstream
systems.

**Bottom line:** for any customer tier that cannot egress to the public internet, all seven managed
brokers are out (none self-hosts, none has an African region). The viable in-cell IdP set is
Keycloak, Zitadel, FusionAuth, authentik, Ory — with Keycloak/FusionAuth as the least surprising
choice for a bank's security review. Keep the collectors off the human IdP entirely.

---

## 1. Managed OIDC brokers (public numbers, 2026-10)

| Vendor | Public price | Residency (EU? Africa?) | Self-host / private cloud | BYO-IdP, SCIM, M2M |
|---|---|---|---|---|
| **WorkOS** | SSO **$125/conn/mo** (1–15), $100 (16–30), $80 (31–50), $65 (51–100), 101+ custom. Directory Sync same. AuthKit free ≤**1M MAU**, then **$2,500/mo per extra 1M**. Audit-log streaming $125/mo; retention $99/mo per 1M events; custom domain $99/mo. | **US only.** DPA authorises transfers "from the EEA, Switzerland, and/or the UK **to the United States**". No EU region, no Africa. | **No.** | SAML + OIDC as SP for any customer IdP; SCIM via Directory Sync; M2M via WorkOS Connect M2M apps + API keys. |
| **Stytch** (now Twilio) | Free: **10k MAU, 5 SSO/SCIM connections, 1k M2M tokens**. Extra connection **$125/mo**. Extra MAU $0.05 (only stated inside an SMS example — see flags). Branding removal $99/mo. | **US only.** Docs: "Stytch operates **exclusively out of U.S. servers**"; GDPR via SCCs + DPF. | **No.** | SAML/OIDC enterprise SSO; SCIM (Okta, Entra); M2M clients + secret rotation. |
| **Clerk** | Pro **$20/mo** (annual) incl 50k MRU, +$0.02/MRU; **1 SSO connection incl**, then **$75/mo each (2–15)**, **$60 (16–100)**; Directory Sync $75/mo from **2027-01-01**. Business $250/mo. | **None.** Security page: "Regional data residency — **Not offered**; US-hosted; EU/UK/Swiss data transferred under the DPF." | **No.** | SAML + OIDC enterprise connections (Okta/Entra/Google/custom); SCIM Directory Sync; machine auth (API keys + M2M tokens). |
| **Auth0 / Okta** | Essentials **$35/mo**, Professional **$240/mo** (both "up to 500 MAU"); enterprise connections/self-service SSO/SCIM are gated to **B2B plans — price not public**. | Public cloud localities **AU, CA, EU (EU, EU-2), JP, US (US, US-3/4/5)**. **Private Cloud** (dedicated, AWS or Azure) exists specifically for residency. No Africa. | **No.** Private Cloud is Okta-run, not customer-run. | SAML/OIDC enterprise connections; SCIM; M2M (client-credentials apps). |
| **Descope** | Free 7.5k MAU / 3 SSO; Pro **$249/mo** (10k MAU, 5 SSO); Growth **$799/mo** (25k MAU, 10 SSO, SCIM, multi-region, admin portal); Enterprise custom. | **US, EU, AP, CA, UK, SG, SA (South America/Brazil)** — region fixed at project creation, cannot be moved. Growth+ only. **No Africa.** | "Private Cloud" = a Descope-provisioned isolated environment (vendor-run), not your DC. | SAML/OIDC (including Descope as IdP for downstream apps); SCIM; M2M access keys. |
| **Kinde** | $0 / **$25** / **$75** / **$250** per mo; **10.5k MAU free**, then **$0.0175/extra MAU**; 50 MAO free then $0.50 each; **1 enterprise SSO connection included** on paid, unlimited on top tiers. No per-connection fee. | **No residency documentation found** (docs contain no region/residency page). Australian company. Treat as single-region until the vendor says otherwise. | **No.** | Custom SAML + Entra/Okta enterprise connections; SCIM provisioning; M2M apps with scopes. |
| **FusionAuth** | **Community: self-host free, unlimited MAU.** FusionAuth Cloud: Starter **$162/mo**, Enterprise **$2,970/mo** (priced against 1,000 MAU, includes hosting). | **Self-host = any region, including African DCs.** Cloud regions not published on the pricing page. | **Yes** — the only vendor in this list with a real self-host build. | SAML v2 + OIDC IdP federation; SCIM server; M2M. |

### Cost shape at 100 cells (one customer IdP connection each)

- Separate WorkOS account per cell: 100 × $125 = **$12.5k/mo (~$150k/yr)**. All orgs under one
  account: 100 conns × $65 = **$6.5k/mo** — but that puts 100 banks' identity data in one tenant.
- Clerk: $75 × 100 = **$7.5k/mo** (one account at 16–100 tier: $6.0k).
- Stytch: **$0** at ≤10k MAU/≤5 connections per workspace — the cheapest by far, and US-only.
- FusionAuth self-host: $0 licence (Community) forever, paid only in your ops time/support.

---

## 2. Self-hostable options

| Product | Licence | What you actually run + back up | Federation to customer IdP (Entra/Google/Okta) | SCIM | Client-credentials / M2M |
|---|---|---|---|---|---|
| **Keycloak** | **Apache-2.0** | JVM (Quarkus) + **PostgreSQL**; container or Operator on k8s; ~monthly patch releases (26.8.x as of Oct 2026), quarterly minors → an upgrade treadmill you must staff. Backup = Postgres dump **+ realm export + keys**. | Yes — "identity brokering" for SAML and OIDC, per-realm. | **Yes, now native**: realm-level SCIM endpoints (enable SCIM for a realm, SCIM base URL, users/groups). This changed recently — most comparison posts still say "no SCIM". | Yes — standard OAuth2 client credentials per client. |
| **Zitadel** | **AGPL-3.0** ⚠ | Single Go container + **PostgreSQL** (CockroachDB optional); official Helm chart; backups = DB only. Lightest ops of the five. | Yes — per-instance IdPs (OIDC, SAML, Entra, Google, LDAP…); "org" per tenant maps cleanly to one cell. | Yes — SCIM 2.0 API + Okta guide. | Yes — client credentials, `private_key_jwt`, PATs. |
| **authentik** | **MIT** core; `authentik/enterprise/` is separately licensed | Python/Django + Postgres + Redis + Go server/outposts + workers — the largest surface area of the five (more moving parts to patch). | Yes — SAML/OIDC "Sources". | **Outbound only** — a SCIM *provider* that pushes users to downstream apps; no inbound SCIM server for a customer IdP to provision into. | Yes — OAuth2 client credentials (creates a service account). |
| **Ory** (Kratos/Hydra/Keto/Oathkeeper) | **Apache-2.0**; OEL is the commercial self-hosted build | 3–4 separate services + Postgres per service + **you write the consent/login app**; highest engineering cost. | SAML only via **Ory Polis** bridge; OIDC/social natively. | SCIM **server is an Ory Network (cloud) feature**; not in the OSS self-host set. | Yes — Hydra client credentials. |
| **Hanko** | **AGPL-3.0** ⚠ | Go + Postgres, small footprint. | SAML enterprise SSO exists, but the docs' prerequisites say **"Hanko Cloud account"** — treat in-cell federation as unproven. | **No.** | **No** first-class M2M/client-credentials. |

---

## 3. "Bring your own IdP" vs "use our IdP as source of truth"

- **All seven managed brokers are SP-side federators** — federating to the customer's Entra/Okta/
  Google *is* the product. That is the first-class "bring your own IdP" flow: WorkOS SSO, Stytch
  SSO, Clerk enterprise connections, Auth0 enterprise connections, Descope SSO, Kinde enterprise
  connections, FusionAuth IdP links.
- **None of them requires the customer to adopt your IdP.** The constraint that bites is different:
  the broker lives in the vendor's cloud, so *every login in a bank's basement needs egress to
  us-east-1 / eu-central-1*. Air-gap kills it; a bank's egress proxy + data-residency review usually
  kills it too.
- **Self-hosted, all except Hanko** let a cell be a full IdP (local break-glass admin accounts) *and*
  broker to the customer IdP per connection. That dual mode is what you want: if the customer's IdP
  is down or the federation is misconfigured, the cell still has a local admin path.
- **Nobody in either list offers an African region.** Nearest options are EU (managed) or
  self-host in `af-south-1` / Azure South Africa North / GCP `africa-south1`.

---

## 4. Workload identity for the collectors

| Option | Runs fully inside the customer env? | Fit | Cost/erosion |
|---|---|---|---|
| **OAuth2 client credentials, one client per connector** | Yes — the cell IdP issues them | Best default. Scope per source (`docs:read:sharepoint`), one client per connector instance so revocation is surgical. | Static secrets; you must build rotation + audit yourself. |
| **mTLS, per-connector certs** (cert-manager / step-ca / Vault PKI) | Yes | Good for on-prem upstreams (file shares, core banking) that speak TLS but not OAuth. | Revocation offline is the pain: no OCSP/CRL reachable in an air-gap → keep certs short-lived (hours/days) and rotate. |
| **SPIFFE/SPIRE** | Yes — SPIRE server + agents run in-cell; no control plane in your cloud | Correct answer if the cell is Kubernetes and you want auto-rotated SVIDs (default TTL 1h) instead of static secrets. | Real ops burden: attestation policy per workload, SPIRE server HA, trust-bundle distribution across cells. Overkill for VMs. |
| **Cloud IAM workload identity federation** (AWS IAM Roles Anywhere, Entra Workload ID, GCP WIF) | Only if the cell is in *that* cloud | Excellent when the bank runs you in their AWS/Azure/GCP tenant: no long-lived secrets at all. | Useless on-prem; binds the cell to one hyperscaler. Roles Anywhere needs an in-cell trust anchor (CA) anyway. |
| **Vault / OpenBao-issued tokens & dynamic secrets** | Yes (per-cell Vault) | The right home for the **~50 upstream credentials**. KV v2 for SaaS OAuth tokens, dynamic creds for DBs, transit for envelope encryption, per-tenant path isolation. | Auto-unseal needs cloud KMS/HSM; in air-gapped banks you're on Shamir unseal = a human on call after every restart. |

**The 50-credentials-per-customer problem, concretely.** Do not put upstream credentials in the IdP.
Model it as `connector_instance → source → credential_set`, store each set in the per-cell secret
store under `tenant/<id>/source/<name>`, encrypt with a per-tenant DEK (envelope), and rotate on a
schedule *and* on demand. The IdP authenticates the connector to **your** app (client credentials);
Vault holds the third-party secrets. Two upstream realities to design for:

- Google OAuth refresh tokens expire (6 months unused; 7 days for apps in testing) and rotate on use
  for public clients — so "store once, forget" breaks silently.
- Slack rotated token issuance to granular scopes with rotation — a bank rotating a service account
  password will break 50 connectors at once unless each connector re-auths independently.

---

## 5. Gotchas that actually bite

1. **Token lifetime vs long-running collectors.** Human access tokens are minutes (Keycloak default
   access-token lifespan is 5 min, realm/client configurable). Collectors run for hours/days: use
   client-credentials tokens with a short TTL plus re-request, *not* a long-lived JWT you can't
   revoke. Never let a collector hold a human refresh token.
2. **JWKS/keys across hundreds of cells.** If every cell has its own signing key, you have hundreds
   of trust anchors to rotate — fine, because rotation is local and can overlap (publish new `kid`,
   keep old for ≥2× token TTL). If you try to share one key across cells, you've built a single
   global blast radius; don't. Budget for a key-rotation runbook per cell and a "keys never leave
   the cell" rule.
3. **Air-gap breaks more than login.** JWKS fetch, OCSP/CRL, SMTP for invites, SMS/email OTP, social
   IdP discovery, licence callbacks — all silently fail. Every one needs an offline path and a
   documented "degraded mode".
4. **Egress dependency is a procurement blocker, not a technical one.** Banks ask "does login work if
   our internet link is down?" A SaaS broker answers no. That single question eliminates WorkOS,
   Stytch, Clerk, Auth0 public cloud, Descope and Kinde for the on-prem tier.
5. **Audit expectations are per-cell, not per-tenant-of-yours.** SOC 2 CC7.2/CC7.3 (monitoring),
   CC6.1/CC6.3 (logical access), ISO/IEC 27001:2022 A.8.15 (logging) / A.8.16 (monitoring), PCI DSS
   v4.0 req. 10 for anything touching card data, and EU banks under DORA Art. 9–10. Practically: the
   cell must emit (a) IdP events — login, MFA, admin/config change, SCIM create/delete — and (b)
   data-access events — which user, which connector, which document, which upstream — to the
   customer's SIEM. Assume they will ask for 12 months retention and tamper-evidence.
6. **Local law, not just GDPR.** Kenya's Data Protection Act 2019 s.48 requires proof of safeguards
   before transfer out of Kenya; Nigeria's NDPA 2023 has its own cross-border regime; South Africa
   POPIA s.72. An EU region is not automatically an answer for a Nairobi or Lagos bank — often the
   answer is "runs in our DC".
7. **AGPL is a real decision, not a footnote.** Zitadel and Hanko are AGPL-3.0: shipping a modified
   binary into a customer's environment triggers source-offer obligations. Keycloak, Ory and
   authentik's core (MIT) avoid that conversation.
8. **The cheapest managed option is the one with the least residency.** Stytch's 5 free SSO/SCIM
   connections per workspace fits "one IdP per cell" perfectly and costs nothing at <10k MAU — and is
   explicitly US-only. Cheap and disqualified at the same time.
9. **Private Cloud ≠ self-host.** Auth0 Private Cloud, Descope Private Cloud and ZITADEL Cloud are
   dedicated but vendor-operated: still egress, still vendor staff with access, still no African DC.
   Only FusionAuth (and the OSS five) put the binary in the customer's hands.
10. **Keycloak's SCIM is new; your architecture docs will be wrong.** Current server docs describe
    realm-level SCIM endpoints; a lot of 2024–2025 comparison content says Keycloak has no SCIM.
    Re-check before you rule it out — and pin the Keycloak minor version per cell, because SCIM
    semantics moved recently.
11. **authentik is MIT but has a patch-heavy SAML surface.** Its 2026 CVE list is dominated by SAML
    source parsing issues (XML signature wrapping, assertion injection, NameID truncation). Not a
    disqualifier, but it means "run the latest patch" is a hard requirement, which fights with
    long-lived bank change windows.
12. **Per-cell identity data is regulated data.** Even a "just SSO" broker stores names, emails,
    group memberships and login metadata. Putting 100 banks' orgs in one vendor tenant creates a
    processor relationship you then have to paper over in every DPA.

---

## Sources (one per claim family)

**Pricing**
- WorkOS pricing (table + volume tiers): https://workos.com/pricing · machine-readable: https://workos.com/pricing.md
- WorkOS M2M apps: https://workos.com/docs/authkit/connect/m2m · API keys: https://workos.com/docs/authkit/api-keys
- Stytch pricing: https://stytch.com/pricing
- Clerk pricing: https://clerk.com/pricing · enterprise SSO/SCIM tiers: https://clerk.com/enterprise-authentication
- Auth0 pricing (incl. Private Cloud Basics): https://auth0.com/pricing
- Descope pricing: https://www.descope.com/pricing
- Kinde pricing: https://kinde.com/pricing
- FusionAuth pricing: https://fusionauth.io/pricing

**Residency**
- WorkOS DPA (cross-border to the US): https://workos.com/legal/dpa
- Stytch data compliance / "exclusively U.S. servers": https://stytch.com/docs/resources/policies/security-and-trust/compliance/data-compliance
- Clerk security page, "Regional data residency — Not offered": https://clerk.com/security · DPA: https://clerk.com/legal/dpa
- Auth0 tenant regions: https://auth0.com/docs/get-started/auth0-overview/create-tenants · Private Cloud: https://auth0.com/docs/deploy-monitor/deploy-private-cloud
- Descope multi-region (region list, immutable after creation): https://docs.descope.com/management/project-settings/multi-regional · architecture: https://docs.descope.com/how-to-deploy-to-production/multi-region-architecture · private cloud: https://docs.descope.com/how-to-deploy-to-production/private-cloud
- Africa hyperscaler regions: https://docs.aws.amazon.com/general/latest/gr/rande.html (af-south-1) · https://cloud.google.com/compute/docs/regions-zones (africa-south1) · https://azure.microsoft.com/en-us/explore/global-infrastructure/geographies/

**Self-hosted facts**
- Keycloak licence: https://github.com/keycloak/keycloak (Apache-2.0) · admin guide incl. SCIM + brokering + token lifespans: https://www.keycloak.org/docs/latest/server_admin/ · release cadence: https://www.keycloak.org/sitemap.xml (26.8.x, Oct 2026)
- Zitadel licence: https://github.com/zitadel/zitadel (AGPL-3.0) · self-hosting: https://zitadel.com/docs/self-hosting/deploy/overview · SCIM: https://zitadel.com/docs/apis/scim2
- authentik licence: https://raw.githubusercontent.com/goauthentik/authentik/main/LICENSE · M2M: https://docs.goauthentik.io/add-secure-apps/providers/oauth2/machine_to_machine · SCIM provider: https://docs.goauthentik.io/add-secure-apps/providers/scim · CVEs: https://docs.goauthentik.io/security/cves/CVE-2026-47201
- Ory: https://www.ory.sh/docs/llms.txt (OSS Apache-2.0, OEL, Polis, Hydra client credentials) · SCIM server scoped to Ory Network: https://www.ory.com/docs/kratos/manage-identities/scim/api-reference
- Hanko licence: https://github.com/teamhanko/hanko (AGPL-3.0) · SAML SSO (Cloud prerequisite): https://docs.hanko.io/guides/enterprise-sso/introduction

**Workload identity**
- SPIFFE: https://spiffe.io/docs/latest/spiffe-about/overview/
- Vault: https://developer.hashicorp.com/vault/docs
- AWS IAM Roles Anywhere: https://docs.aws.amazon.com/rolesanywhere/latest/userguide/introduction.html
- Entra Workload Identity Federation: https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation
- GCP Workload Identity Federation: https://cloud.google.com/iam/docs/workload-identity-federation
- Google OAuth refresh-token expiry/rotation: https://developers.google.com/identity/protocols/oauth2
- Slack token rotation: https://api.slack.com/authentication/rotation

**Compliance**
- SOC 2 (AICPA): https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2
- ISO/IEC 27001: https://www.iso.org/standard/27001
- PCI DSS: https://www.pcisecuritystandards.org/standards/pci-dss/
- GDPR (Ch. V transfers): https://eur-lex.europa.eu/eli/reg/2016/679/oj
- Kenya Data Protection Act 2019: http://kenyalaw.org/kl/fileadmin/pdfdownloads/Acts/2019/DataProtectionAct_No24of2019.pdf
- Nigeria NDPC: https://www.ndpc.gov.ng/ · POPIA: https://www.gov.za/documents/protection-personal-information-act

**Flags — stale or contradictory public info**
- **Clerk SSO fees:** Nov 2024 post "eliminates SSO fees" (https://clerk.com/blog/clerk-launches-easio-sso-and-drops-all-sso-fees) vs. current $75/$60 per connection (https://clerk.com/pricing, https://clerk.com/enterprise-authentication). Current page wins; the blog is stale.
- **Auth0:** the $35/$240 numbers do not buy enterprise connections — those need a B2B plan with unpublished pricing. Any TCO comparison using $240 for SSO is wrong.
- **FusionAuth:** $162/$2,970 are *Cloud* prices (hosting included, 1,000-MAU reference). The self-host Community build is free; don't quote $2,970 as a licence cost.
- **Stytch MAU rate:** $0.05/MAU appears only inside an SMS pricing example, never as a headline rate. Confirm with sales before modelling.
- **Kinde residency:** no public doc either way. Absence of evidence, not evidence of absence.
- **Keycloak SCIM:** newly documented; most third-party comparisons are outdated.
