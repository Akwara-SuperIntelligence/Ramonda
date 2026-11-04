"""Liveness and readiness endpoints.

Sources
    BUILD §3 — liveness and readiness endpoints; a dependency failure degrades

Delta
    A standard-library server for the worker and the consumer. Readiness checks
    Postgres; the process does not crash when the database is down.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg

from agent_service.activities import _dsn
from agent_service.metrics import metrics_text


def start_health_server(port: int, name: str = "agent") -> ThreadingHTTPServer:
    """Start the server on a daemon thread. Port 0 picks a free port."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                body, status, ctype = f"{name} alive", 200, "text/plain"
            elif self.path == "/readyz":
                try:
                    with psycopg.connect(_dsn(), connect_timeout=2) as conn:
                        conn.execute("select 1")
                    body, status, ctype = f"{name} ready", 200, "text/plain"
                except Exception:
                    body, status, ctype = (
                        f"{name} not ready: database unavailable",
                        503,
                        "text/plain",
                    )
            elif self.path == "/metrics":
                try:
                    body, status, ctype = metrics_text(), 200, "text/plain"
                except Exception:
                    body, status, ctype = (
                        "metrics unavailable",
                        503,
                        "text/plain",
                    )
            else:
                body, status, ctype = "not found", 404, "text/plain"
            payload = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
