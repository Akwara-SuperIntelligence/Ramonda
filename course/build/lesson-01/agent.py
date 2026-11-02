#!/usr/bin/env python3
"""Lesson 01: the smallest honest agent loop.

The whole agent is three steps repeated:

    1. send messages + tool schemas to the model
    2. execute whatever tools it asks for
    3. append the results and go again

Everything else in this course exists because step 3 lives in process memory,
and processes die.

Run it:

    .venv/bin/python build/lesson-01/agent.py "your task"

Then read the lesson: lessons/0001-the-loop-that-dies.html
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
ROOT = HERE.parents[1]                  # repo root
WORKSPACE = HERE / "workspace"          # the agent's working directory
STATE = HERE / "state" / "transcript.json"

SYSTEM = """You are a small agent running on a server.
You have a shell and a file writer. Both operate inside your workspace directory.

Work step by step: inspect before you write, verify after you write.
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


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------

def load_env() -> None:
    """Read the repo .env without needing python-dotenv."""
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


# --------------------------------------------------------------------------
# tools — the model asks, this code executes
# --------------------------------------------------------------------------

def _clip(text: str, limit: int = 4000) -> str:
    """Long outputs eat the context window. Keep the ends, drop the middle."""
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
# state — written after every completed step, which is *not* the same as durable
# --------------------------------------------------------------------------

def save(messages: list[dict]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(messages, indent=2))
    tmp.replace(STATE)


def load() -> list[dict]:
    if not STATE.exists():
        return []
    messages = json.loads(STATE.read_text())
    # A crash can leave an assistant tool_call with no tool result behind it.
    # The API rejects that, so drop dangling tail calls and orphan tool messages.
    clean: list[dict] = []
    for i, message in enumerate(messages):
        if message.get("role") == "assistant" and message.get("tool_calls"):
            ids = {c["id"] for c in message["tool_calls"]}
            have = {
                m.get("tool_call_id")
                for m in messages[i + 1 :]
                if m.get("role") == "tool"
            }
            if not ids <= have:
                break  # stop at the first incomplete step
        if message.get("role") == "tool" and not any(
            c["id"] == message.get("tool_call_id")
            for m in clean
            if m.get("role") == "assistant"
            for c in (m.get("tool_calls") or [])
        ):
            continue
        clean.append(message)
    return clean


# --------------------------------------------------------------------------
# the loop
# --------------------------------------------------------------------------

def run(task: str, max_steps: int, crash_on: str, resume: bool) -> None:
    client, model = make_client()
    WORKSPACE.mkdir(exist_ok=True)

    messages = load() if resume else []
    if not messages or messages[-1].get("content") != task:
        messages.append({"role": "user", "content": task})
        save(messages)  # the run exists on disk before any tool can fail

    print(f"model: {model}\nworkspace: {WORKSPACE}\ntask: {task}\n")

    for step in range(1, max_steps + 1):
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM}, *messages],
            tools=TOOLS,
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            save(messages)
            print("\n" + (message.content or "").strip())
            print(f"\n[done in {step - 1} tool rounds]")
            return

        for call in message.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments or "{}")
            print(f"[{step}] {name} {json.dumps(args)[:160]}")

            result = execute(name, args)

            if name == crash_on:
                print(f"\n*** process killed after tool '{name}' ran, before its result was recorded ***")
                print("*** side effects are on disk; the agent never learned what happened ***\n")
                sys.stdout.flush()
                os._exit(1)  # a real death: no cleanup, no save

            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )
            print(f"    -> {result.splitlines()[0][:160] if result else '(no output)'}")
            save(messages)  # checkpoint after each completed step

    print(f"\n[stopped: hit max_steps={max_steps}]")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument(
        "--crash-on",
        default="",
        help="die after the first call to this tool, e.g. write_file",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run(args.task, args.max_steps, args.crash_on, args.resume)


if __name__ == "__main__":
    main()
