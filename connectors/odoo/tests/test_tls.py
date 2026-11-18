import os
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "deploy/certs/generate.sh"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _handshake(port: int, ca: Path, cert: Path | None, key: Path | None) -> bytes:
    context = ssl.create_default_context(cafile=ca)
    if cert is not None and key is not None:
        context.load_cert_chain(cert, key)
    raw = socket.create_connection(("127.0.0.1", port), 2)
    tls = None
    try:
        tls = context.wrap_socket(raw, server_hostname="localhost")
        tls.sendall(b"POST /mcp HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n")
        return tls.recv(64)
    finally:
        if tls is None:
            raw.close()
        else:
            tls.close()


def assert_rejected(
    port: int, ca: Path, cert: Path | None, key: Path | None, who: str
) -> None:
    try:
        body = _handshake(port, ca, cert, key)
    except (ssl.SSLError, BrokenPipeError, ConnectionResetError):
        return
    if body.startswith(b"HTTP/"):
        raise AssertionError(f"accepted a {who}")


def test_public_bind_without_tls_exits() -> None:
    env = os.environ.copy()
    for name in ("ODOO_TLS_CERT", "ODOO_TLS_KEY", "ODOO_TLS_CLIENT_CA"):
        env.pop(name, None)
    env["ODOO_MCP_HOST"] = "0.0.0.0"
    env["ODOO_MCP_PORT"] = "9"
    result = subprocess.run(
        [sys.executable, "-m", "odoo"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert "ODOO_TLS_CERT, ODOO_TLS_KEY, and ODOO_TLS_CLIENT_CA are required" in result.stderr


def test_connector_rejects_a_caller_without_the_gateway_certificate(tmp_path: Path) -> None:
    subprocess.run([str(SCRIPT), str(tmp_path)], check=True)
    other = tmp_path / "other"
    subprocess.run([str(SCRIPT), str(other)], check=True)
    port = _free_port()
    env = os.environ.copy()
    env.update(
        {
            "ODOO_MCP_HOST": "127.0.0.1",
            "ODOO_MCP_PORT": str(port),
            "ODOO_TLS_CERT": str(tmp_path / "odoo-connector.crt"),
            "ODOO_TLS_KEY": str(tmp_path / "odoo-connector.key"),
            "ODOO_TLS_CLIENT_CA": str(tmp_path / "ca.crt"),
        }
    )
    err = (tmp_path / "server.err").open("w")
    server = subprocess.Popen(
        [sys.executable, "-m", "odoo"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=err,
    )
    ca = tmp_path / "ca.crt"
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                accepted = _handshake(port, ca, tmp_path / "gateway.crt", tmp_path / "gateway.key")
                break
            except OSError:
                time.sleep(0.05)
        else:
            err.flush()
            detail = (tmp_path / "server.err").read_text()
            raise AssertionError(detail or "connector did not start")
        if not accepted.startswith(b"HTTP/1.1"):
            raise AssertionError(accepted)
        assert_rejected(port, ca, None, None, "caller with no client certificate")
        assert_rejected(
            port,
            ca,
            other / "gateway.crt",
            other / "gateway.key",
            "client certificate from another CA",
        )
    finally:
        server.terminate()
        server.wait(timeout=5)
        err.close()
