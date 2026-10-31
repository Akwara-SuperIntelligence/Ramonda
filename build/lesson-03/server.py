#!/usr/bin/env python3
"""Lesson 03: a thick server.

This is the only place with a model key, tools, and history. The client
sends text and gets text. Nothing else crosses the boundary.

Run it in terminal A:

    .venv/bin/python build/lesson-03/server.py

Then use client.py in terminal B.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from openai import OpenAI

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORKSPACE = HERE / "workspace"
STATE = HERE / "state" / "history.json"
HOST, PORT = "127.0.0.1", 8765

SYSTEM = """You are an agent on a server. You have a shell in your workspace.
Work step by step: inspect, write, verify.
Do not ask the user questions; do the task.
When the task is finished, reply with a one-paragraph summary.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "Run a shell command in your workspace. Use it to list and read files, "
                "run python, and check results. 30 second limit. Returns exit code and output."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to run, e.g. 'ls -la'."}
                },
                "required": ["command"],
            },
        },
    }
]

LOCK = threading.Lock()
CLIENT: OpenAI | None = None
MODEL = ""


def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def model() -> tuple[OpenAI, str]:
    global CLIENT, MODEL
    if CLIENT is None:
        load_env()
        if os.environ.get("DEEPSEEK_API_KEY"):
            CLIENT = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
            MODEL = os.environ.get("MODEL", "deepseek-chat")
        elif os.environ.get("OPENROUTER_API_KEY"):
            CLIENT = OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1")
            MODEL = os.environ.get("MODEL", "deepseek/deepseek-chat")
        else:
            raise RuntimeError("No model key in .env")
    return CLIENT, MODEL


def execute(command: str) -> str:
    try:
        proc = subprocess.run(
            command, shell=True, cwd=WORKSPACE, capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return "exit code: timeout (30s)"
    out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
    if len(out) > 4000:
        out = out[:1500] + f"\n[... {len(out) - 4000} chars clipped ...]\n" + out[-2500:]
    return f"exit code: {proc.returncode}\n{out}".strip()


def load_history() -> list[dict]:
    if not STATE.exists():
        return []
    return json.loads(STATE.read_text())


def save(messages: list[dict]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(messages, indent=2))
    tmp.replace(STATE)


def run_turn(text: str) -> str:
    WORKSPACE.mkdir(exist_ok=True)
    messages = load_history()
    messages.append({"role": "user", "content": text})
    save(messages)

    client, name = model()
    for step in range(1, 9):
        response = client.chat.completions.create(
            model=name,
            messages=[{"role": "system", "content": SYSTEM}, *messages],
            tools=TOOLS,
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))
        save(messages)

        if not message.tool_calls:
            return message.content or ""

        for call in message.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            print(f"  [{step}] {call.function.name} {args.get('command', '')[:100]}", flush=True)
            result = execute(args.get("command", ""))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            save(messages)

    return "(stopped at the step limit)"


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if self.path != "/send":
            return self._json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            text = (json.loads(self.rfile.read(length) or b"{}").get("text") or "").strip()
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad json"})
        if not text:
            return self._json(400, {"error": "text required"})

        print(f"\n[message] {text}", flush=True)
        try:
            with LOCK:
                reply = run_turn(text)
        except Exception as exc:  # keep the server alive for the demo
            reply = f"server error: {exc}"
        print(f"[reply] {reply[:200]}", flush=True)

        try:
            self._json(200, {"reply": reply})
        except (BrokenPipeError, ConnectionResetError):
            print("[client left; the turn is already saved]", flush=True)

    def do_GET(self) -> None:
        if self.path != "/history":
            return self._json(404, {"error": "not found"})
        messages = [
            {"role": m["role"], "content": m.get("content", "")}
            for m in load_history()
            if m.get("role") in ("user", "assistant") and m.get("content")
        ]
        self._json(200, {"messages": messages})

    def log_message(self, fmt: str, *args) -> None:
        pass


class Server(ThreadingHTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    WORKSPACE.mkdir(exist_ok=True)
    print(f"listening on http://{HOST}:{PORT}", flush=True)
    Server((HOST, PORT), Handler).serve_forever()
