import os
import ssl

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

from .server import mcp


def _tls() -> tuple[str, str, str] | None:
    cert = os.environ.get("ODOO_TLS_CERT", "")
    key = os.environ.get("ODOO_TLS_KEY", "")
    client_ca = os.environ.get("ODOO_TLS_CLIENT_CA", "")
    if not cert and not key and not client_ca:
        return None
    if not (cert and key and client_ca):
        raise SystemExit("ODOO_TLS_CERT, ODOO_TLS_KEY, and ODOO_TLS_CLIENT_CA are set together")
    return cert, key, client_ca


def main() -> None:
    host = os.environ.get("ODOO_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("ODOO_MCP_PORT", "8000"))
    tls = _tls()
    if tls is None and host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("ODOO_TLS_CERT, ODOO_TLS_KEY, and ODOO_TLS_CLIENT_CA are required")
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"odoo-connector:{port}", "127.0.0.1:*", "localhost:*"],
    )
    if tls is None:
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            json_response=True,
            transport_security=security,
        )
        return
    cert, key, client_ca = tls
    app = mcp.streamable_http_app(
        json_response=True,
        transport_security=security,
        host=host,
    )
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="warning",
        ssl_certfile=cert,
        ssl_keyfile=key,
        ssl_ca_certs=client_ca,
        ssl_cert_reqs=ssl.CERT_REQUIRED,
    )


if __name__ == "__main__":
    main()
