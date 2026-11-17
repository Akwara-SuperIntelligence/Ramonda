# Certificates for a stamp

Local Compose uses a dev CA. Anything else supplies certificates you operate. The gateway reads the files when it starts. It does not reload them. Replace the files, then restart the gateway and the connector.

## Local Compose

Run `deploy/certs/generate.sh` before `docker compose up`. The script writes `deploy/certs/out/` and does nothing if `ca.crt` is already there. Delete that directory to replace the dev certificates. They expire after 825 days. The private keys stay in that directory. Do not commit them.

`deploy/compose.yaml` sets `RAMONDA_STAMP=local`. That value is the laptop stamp. It trusts the dev CA, whose subject is `CN=Ramonda Dev CA`.

Remove `RAMONDA_STAMP: local` from `deploy/compose.yaml` before any server deploy. A server that still has that line stays on the laptop stamp and trusts the dev CA.

Trust `deploy/certs/out/ca.crt` in a browser that signs in through Keycloak. Add `127.0.0.1 keycloak` to the hosts file. The issuer host stays `keycloak`.

## Non-local stamp

Leave `RAMONDA_STAMP` unset. Any value other than `local` is the same as unset. The gateway then refuses to start unless all of the following hold:

- `KEYCLOAK_ISSUER`, `ODOO_MCP_URL`, and `OPENBAO_ADDR` are `https` URLs.
- `GATEWAY_TLS_CA` is a PEM file of one or more certificates. The gateway uses it to verify Keycloak, the Odoo connector, and OpenBao. The file must not be the dev CA.
- `GATEWAY_TLS_CERT` and `GATEWAY_TLS_KEY` are the gateway client certificate and its PKCS #8 private key, in PEM. The connector demands this certificate during the TLS handshake.
- `ODOO_TLS_CERT` and `ODOO_TLS_KEY` are the connector server certificate and its private key. A subject alternative name must match the host in `ODOO_MCP_URL`.
- `ODOO_TLS_CLIENT_CA` is the certificate that verifies the gateway client certificate. Issue that client certificate from a CA that signs no other client.

OpenBao on this stamp is an HTTPS listener with a certificate that chains to `GATEWAY_TLS_CA`. The laptop Compose file runs OpenBao in dev mode on HTTP, and only `RAMONDA_STAMP=local` allows that.

Renewal is replace the PEM files and restart the gateway and the connector. This repository does not run a certificate manager. The dev script is not a source of certificates for this stamp. Copying `deploy/compose.yaml` onto a server without removing `RAMONDA_STAMP=local` still selects the laptop stamp.
