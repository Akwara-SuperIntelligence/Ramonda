#!/usr/bin/env python3
"""Lesson 04: the router. Triggers wake the agent.

    trigger.py  ->  router.py (:8766)  ->  server.py (:8765)

The router is the front door. It receives an event, drops duplicates, and
forwards the text to the agent server in the background. The agent server
from lesson 03 does not change.

Run this after the lesson 03 server:

    .venv/bin/python build/lesson-04/router.py
"""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEEN = HERE / "state" / "seen.json"
AGENT = "http://127.0.0.1:8765"
HOST, PORT = "127.0.0.1", 8766

LOCK = threading.Lock()


def claim(event_id: str) -> bool:
    """True if this id is new. False if it was already handled."""
    with LOCK:
        seen = json.loads(SEEN.read_text()) if SEEN.exists() else []
        if event_id in seen:
            return False
        seen.append(event_id)
        SEEN.parent.mkdir(parents=True, exist_ok=True)
        SEEN.write_text(json.dumps(seen))
        return True


def forward(text: str) -> None:
    request = urllib.request.Request(
        AGENT + "/send",
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            reply = json.load(response)["reply"]
        print(f"[done] {reply[:160]}", flush=True)
    except Exception as exc:
        print(f"[forward failed] {exc}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if self.path != "/event":
            return self._json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad json"})

        event_id = str(body.get("id") or "").strip()
        text = (body.get("text") or "").strip()
        source = body.get("source") or "unknown"
        if not event_id or not text:
            return self._json(400, {"error": "id and text required"})

        if not claim(event_id):
            print(f"[duplicate] {event_id}", flush=True)
            return self._json(200, {"status": "duplicate"})

        print(f"[event] {event_id} from {source}", flush=True)
        threading.Thread(target=forward, args=(text,), daemon=True).start()
        self._json(202, {"status": "accepted"})

    def log_message(self, fmt: str, *args) -> None:
        pass


class Router(ThreadingHTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    print(f"router on http://{HOST}:{PORT} -> {AGENT}", flush=True)
    Router((HOST, PORT), Handler).serve_forever()
