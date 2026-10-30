#!/usr/bin/env python3
"""Lesson 02: write the intent before you act.

Lesson 01 saved the tool result. A crash between the side effect and the save
lost the knowledge. This version writes two journal entries around every call:

    intent  -> execute -> result

If the process dies in the middle, the journal still says a call may have run.
On resume, the harness tells the model that, and the model checks before it
repeats.

Run it:

    .venv/bin/python build/lesson-02/agent.py "your task"

Then read the lesson: lessons/0002-write-it-down-first.html
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from openai import OpenAI

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORKSPACE = HERE / "workspace"
STATE = HERE / "state" / "transcript.json"
JOURNAL = HERE / "state" / "journal.jsonl"

SYSTEM = """You are a small agent running on a server.
You have a shell and a file writer. Both operate inside your workspace directory.

Work step by step: inspect before you write, verify after you write.
If a tool result starts with INTERRUPTED, that call may have completed before
the process stopped. Check the workspace before you repeat it.
Do not ask the user questions; do the task.
When the task is finished, reply with a one-paragraph summary of what you did.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "Run a shell command in your workspace. Use it to list files, "
                "read them, run python, and check results. 30 second limit. "
                "Returns exit code, stdout and stderr."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to run, e.g. 'ls -la'."}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create or overwrite a file in your workspace. Paths are relative "
                "to the workspace root. Creates parent directories."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path, e.g. 'notes/plan.md'."},
                    "content": {"type": "string", "description": "Full file contents."},
                },
                "required": ["path", "content"],
            },
        },
    },
]


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


def make_client() -> tuple[OpenAI, str]:
    load_env()
    if os.environ.get("DEEPSEEK_API_KEY"):
        return (
            OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com"),
            os.environ.get("MODEL", "deepseek-chat"),
        )
    if os.environ.get("OPENROUTER_API_KEY"):
        return (
            OpenAI(
                api_key=os.environ["OPENROUTER_API_KEY"],
                base_url="https://openrouter.ai/api/v1",
            ),
            os.environ.get("MODEL", "deepseek/deepseek-chat"),
        )
    sys.exit("No model key found. Put DEEPSEEK_API_KEY or OPENROUTER_API_KEY in .env")


def _clip(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:1500]}\n\n[... {len(text) - limit} chars clipped ...]\n\n{text[-limit + 1500:]}"


def execute(name: str, args: dict) -> str:
    if name == "run_shell":
        try:
            proc = subprocess.run(
                args["command"],
                shell=True,
                cwd=WORKSPACE,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return "exit code: timeout (30s)"
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        return _clip(f"exit code: {proc.returncode}\n{out}".strip())

    if name == "write_file":
        target = (WORKSPACE / args["path"]).resolve()
        if WORKSPACE.resolve() not in target.parents and target != WORKSPACE.resolve():
            return "error: path escapes the workspace"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(args["content"])
        return f"wrote {len(args['content'])} chars to {args['path']}"

    return f"error: unknown tool {name}"


# --------------------------------------------------------------------------
# the journal: append-only, one JSON object per line
# --------------------------------------------------------------------------

def journal(event: dict) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a") as f:
        f.write(json.dumps(event) + "\n")


def read_journal() -> list[dict]:
    if not JOURNAL.exists():
        return []
    return [json.loads(line) for line in JOURNAL.read_text().splitlines() if line.strip()]


def save(messages: list[dict]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(messages, indent=2))
    tmp.replace(STATE)


def load() -> list[dict]:
    """Load the transcript, then reconcile the last tool call against the journal."""
    if not STATE.exists():
        return []
    messages = json.loads(STATE.read_text())

    last = messages[-1] if messages else None
    if not (last and last.get("role") == "assistant" and last.get("tool_calls")):
        return messages

    # shortcut: only the tail call can be incomplete in this toy
    intents = {e["call_id"]: e for e in read_journal() if e["type"] == "intent"}
    finished = {e["call_id"] for e in read_journal() if e["type"] == "result"}
    answered = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}

    for call in last["tool_calls"]:
        cid = call["id"]
        if cid in answered:
            continue
        if cid in finished:
            content = "The call completed, but its result was not saved. Check the workspace."
        elif cid in intents:
            content = (
                "INTERRUPTED: this call may have completed before the process stopped. "
                "Check the workspace before you repeat it."
            )
        else:
            content = "NOT EXECUTED: the process stopped before this call ran. It is safe to retry."
        messages.append({"role": "tool", "tool_call_id": cid, "content": content})

    return messages


def run(task: str, max_steps: int, crash_on: str, resume: bool) -> None:
    client, model = make_client()
    WORKSPACE.mkdir(exist_ok=True)

    messages = load() if resume else []
    if not messages:
        messages.append({"role": "user", "content": task})
        save(messages)

    if resume:
        intents = [e for e in read_journal() if e["type"] == "intent"]
        finished = {e["call_id"] for e in read_journal() if e["type"] == "result"}
        pending = [e for e in intents if e["call_id"] not in finished]
        print(f"journal: {len(intents)} intents, {len(pending)} without a result")
        for e in pending:
            print(f"  pending: {e['tool']} {json.dumps(e['args'])[:100]}")

    print(f"model: {model}\nworkspace: {WORKSPACE}\ntask: {task}\n")

    for step in range(1, max_steps + 1):
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM}, *messages],
            tools=TOOLS,
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))
        save(messages)  # the decision is on disk before anything runs

        if not message.tool_calls:
            print("\n" + (message.content or "").strip())
            print(f"\n[done in {step - 1} tool rounds]")
            return

        for call in message.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments or "{}")
            print(f"[{step}] {name} {json.dumps(args)[:160]}")

            journal({"type": "intent", "call_id": call.id, "tool": name, "args": args})
            result = execute(name, args)

            if name == crash_on:
                print(f"\n*** process killed after tool '{name}' ran, before its result was journaled ***")
                print("*** the journal has an intent; the result is missing ***\n")
                sys.stdout.flush()
                os._exit(1)

            journal({"type": "result", "call_id": call.id, "result": result})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            print(f"    -> {result.splitlines()[0][:160] if result else '(no output)'}")
            save(messages)

    print(f"\n[stopped: hit max_steps={max_steps}]")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--crash-on", default="", help="die after the first call to this tool")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run(args.task, args.max_steps, args.crash_on, args.resume)


if __name__ == "__main__":
    main()
