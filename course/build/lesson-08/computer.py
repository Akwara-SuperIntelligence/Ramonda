#!/usr/bin/env python3
"""Lesson 08: the agent's machine, as a service.

    POST /run      {"command": "..."}   run in the box
    POST /reset                          wipe the box
    POST /snapshot                       copy the box to snapshot/
    POST /restore                        copy snapshot/ back to the box
    GET  /tree                           list files in the box

The box is a directory with a service in front of it. It is NOT a virtual
machine. Commands can still reach the host. Do not run untrusted code here.
The interface is the lesson; Firecracker is the real implementation.

    .venv/bin/python build/lesson-08/computer.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOX = HERE / "box"
SNAP = HERE / "snapshot"
HOST, PORT = "127.0.0.1", 8767


def run(command: str) -> str:
    BOX.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=BOX,
            capture_output=True,
            text=True,
            timeout=30,
            env={"HOME": str(BOX), "TMPDIR": str(BOX), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        )
    except subprocess.TimeoutExpired:
        return "exit code: timeout (30s)"
    out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
    out = f"exit code: {proc.returncode}\n{out}".strip()
    if len(out) > 4000:
        out = out[:1500] + f"\n[... {len(out) - 4000} chars clipped ...]\n" + out[-2500:]
    return out


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path != "/tree":
            return self._json(404, {"error": "not found"})
        files = sorted(str(p.relative_to(BOX)) for p in BOX.rglob("*") if p.is_file())
        self._json(200, {"files": files})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad json"})

        if self.path == "/run":
            command = (body.get("command") or "").strip()
            if not command:
                return self._json(400, {"error": "command required"})
            print(f"[run] {command[:100]}", flush=True)
            return self._json(200, {"output": run(command)})

        if self.path == "/reset":
            shutil.rmtree(BOX, ignore_errors=True)
            BOX.mkdir(parents=True)
            print("[reset] box is empty", flush=True)
            return self._json(200, {"status": "reset"})

        if self.path == "/snapshot":
            shutil.rmtree(SNAP, ignore_errors=True)
            shutil.copytree(BOX, SNAP)
            print("[snapshot] saved", flush=True)
            return self._json(200, {"status": "snapshot"})

        if self.path == "/restore":
            shutil.rmtree(BOX, ignore_errors=True)
            shutil.copytree(SNAP, BOX)
            print("[restore] box restored", flush=True)
            return self._json(200, {"status": "restore"})

        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args) -> None:
        pass


class Machine(ThreadingHTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    BOX.mkdir(parents=True, exist_ok=True)
    print(f"machine on http://{HOST}:{PORT} (box: {BOX})", flush=True)
    Machine((HOST, PORT), Handler).serve_forever()
