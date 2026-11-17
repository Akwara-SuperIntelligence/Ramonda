import os

from mcp.server.transport_security import TransportSecuritySettings

from .server import mcp


def main() -> None:
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("ODOO_MCP_HOST", "0.0.0.0"),
        port=int(os.environ.get("ODOO_MCP_PORT", "8000")),
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["odoo-connector:8000", "127.0.0.1:*", "localhost:*"],
        ),
    )


if __name__ == "__main__":
    main()
