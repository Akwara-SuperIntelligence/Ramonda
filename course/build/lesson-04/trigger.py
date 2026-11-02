#!/usr/bin/env python3
"""Lesson 04: a trigger. No human, no client — just an event.

    .venv/bin/python trigger.py "text"
    .venv/bin/python trigger.py --every 15 "text"
    .venv/bin/python trigger.py --replay "text"

It posts to the router, which wakes the agent server.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

ROUTER = "http://127.0.0.1:8766/event"
DEFAULT_TEXT = (
    "Check the workspace. If heartbeat.md is missing, create it with the current UTC time. "
    "Otherwise append one line with the current UTC time."
)


def send(event_id: str, text: str) -> None:
    request = urllib.request.Request(
        ROUTER,
        data=json.dumps({"id": event_id, "text": text, "source": "trigger"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(event_id, json.load(response))
    except urllib.error.URLError as exc:
        sys.exit(f"router not reachable: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="?", default=DEFAULT_TEXT)
    parser.add_argument("--every", type=int, default=0, help="send an event every N seconds")
    parser.add_argument("--replay", action="store_true", help="send the same id twice")
    args = parser.parse_args()

    if args.replay:
        send("replay-demo", args.text)
        send("replay-demo", args.text)
        return

    if args.every:
        try:
            while True:
                send(f"cron-{time.time_ns()}", args.text)
                time.sleep(args.every)
        except KeyboardInterrupt:
            print("\nstopped")
        return

    send(f"manual-{time.time_ns()}", args.text)


if __name__ == "__main__":
    main()
