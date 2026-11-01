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
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from openai import OpenAI

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORKSPACE = HERE / "workspace"
STATE = HERE / "state" / "history.json"
MEMORY = HERE / "memory"
PROFILE = MEMORY / "profile.md"
LOGS = MEMORY / "log"
HOST, PORT = "127.0.0.1", 8765

SYSTEM = """You are an agent on a server. You have a shell in your workspace.
Work step by step: inspect, write, verify.
You can delegate a focused task to a helper. The helper has its own context and
shell. You get back only its report. Delegate work that needs many shell calls
or reads a lot of data.
You have memory tools. Use remember for durable facts about the user. Use recall
to search your dated work logs when the user asks about past work.
Do not ask the user questions; do the task.
When the task is finished, reply with a one-paragraph summary.
"""

HELPER_SYSTEM = """You are a helper agent. You have one shell in the same workspace.
Do the task you are given. Inspect, compute, verify.
Do not delegate. Do not ask questions.
When finished, reply with a short report: findings, file paths, and anything unresolved.
"""

RUN_SHELL = {
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

DELEGATE = {
    "type": "function",
    "function": {
        "name": "delegate",
        "description": (
            "Give a focused, self-contained task to a helper with fresh context and a shell. "
            "The helper cannot see this conversation, so include all needed details. "
            "Returns only the helper's short report."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Full instructions for the helper."}
            },
            "required": ["task"],
        },
    },
}

REMEMBER = {
    "type": "function",
    "function": {
        "name": "remember",
        "description": (
            "Save a durable fact about the user to memory. Use for preferences, names, "
            "and recurring constraints. The fact is added to every future request."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "One short fact, e.g. 'Prefers bullet points.'"}
            },
            "required": ["fact"],
        },
    },
}

RECALL = {
    "type": "function",
    "function": {
        "name": "recall",
        "description": (
            "Search your dated work logs for a word or phrase. Returns matching lines "
            "with file names. Use when the user asks about past work."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A word or phrase to search for."}
            },
            "required": ["query"],
        },
    },
}

TOOLS = [RUN_SHELL, DELEGATE, REMEMBER, RECALL]

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


def profile_block() -> str:
    if not PROFILE.exists():
        return ""
    text = PROFILE.read_text().strip()
    return "\n\nWHAT YOU KNOW ABOUT THE USER (memory):\n" + text if text else ""


def remember(fact: str) -> str:
    fact = fact.strip()
    if not fact:
        return "error: empty fact"
    if len(fact) > 500:
        return "error: fact too long"
    PROFILE.parent.mkdir(parents=True, exist_ok=True)
    with PROFILE.open("a") as f:
        f.write(f"- {fact}\n")
    return f"remembered: {fact}"


def recall(query: str) -> str:
    query = query.strip()
    if not query:
        return "error: empty query"
    if not LOGS.exists():
        return "no logs yet"
    hits: list[str] = []
    for path in sorted(LOGS.glob("*.md"), reverse=True):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if query.lower() in line.lower():
                hits.append(f"{path.name}:{n}: {line.strip()[:200]}")
                if len(hits) >= 20:
                    break
        if len(hits) >= 20:
            break
    return "\n".join(hits) if hits else f"no matches for {query!r}"


def log_turn(text: str, reply: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    path = LOGS / f"{date.today().isoformat()}.md"
    with path.open("a") as f:
        f.write(f"\n## {datetime.now().strftime('%H:%M')}\nUSER: {text}\nAGENT: {reply}\n")


def approx_tokens(messages: list[dict]) -> int:
    return sum(len(json.dumps(m)) for m in messages) // 4


def run_helper(task: str) -> tuple[str, int, int]:
    """A second loop with its own context. Only the report comes back."""
    client, name = model()
    messages: list[dict] = [{"role": "user", "content": task}]
    calls = 0
    tokens = 0

    for _ in range(1, 11):
        response = client.chat.completions.create(
            model=name,
            messages=[{"role": "system", "content": HELPER_SYSTEM}, *messages],
            tools=[RUN_SHELL],
        )
        tokens += response.usage.total_tokens
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            return (message.content or ""), calls, tokens

        for call in message.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            result = execute(args.get("command", ""))
            calls += 1
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    return "(helper hit the step limit)", calls, tokens


def run_turn(text: str) -> str:
    WORKSPACE.mkdir(exist_ok=True)
    messages = load_history()
    messages.append({"role": "user", "content": text})
    save(messages)

    client, name = model()
    for step in range(1, 9):
        response = client.chat.completions.create(
            model=name,
            messages=[{"role": "system", "content": SYSTEM + profile_block()}, *messages],
            tools=TOOLS,
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))
        save(messages)

        if not message.tool_calls:
            reply = message.content or ""
            log_turn(text, reply)
            print(f"  [main] {len(messages)} messages, ~{approx_tokens(messages)} tokens", flush=True)
            return reply

        for call in message.tool_calls:
            name_ = call.function.name
            args = json.loads(call.function.arguments or "{}")
            print(f"  [{step}] {name_} {json.dumps(args)[:100]}", flush=True)
            if name_ == "delegate":
                result, calls, tokens = run_helper(args.get("task", ""))
                print(f"  [helper] {calls} tool calls, {tokens} tokens", flush=True)
            elif name_ == "remember":
                result = remember(args.get("fact", ""))
            elif name_ == "recall":
                result = recall(args.get("query", ""))
            else:
                result = execute(args.get("command", ""))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            save(messages)

    print(f"  [main] {len(messages)} messages, ~{approx_tokens(messages)} tokens", flush=True)
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
            if m.get("role") == "user"
            or (m.get("role") == "assistant" and not m.get("tool_calls") and m.get("content"))
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
