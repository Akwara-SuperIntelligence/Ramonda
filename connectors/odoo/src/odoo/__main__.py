import os

from mcp.server.transport_security import TransportSecuritySettings

from .server import mcp


def main() -> None:
    port = int(os.environ.get("ODOO_MCP_PORT", "8000"))
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("ODOO_MCP_HOST", "0.0.0.0"),
        port=port,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[f"odoo-connector:{port}", "127.0.0.1:*", "localhost:*"],
        ),
    )


if __name__ == "__main__":
    main()
