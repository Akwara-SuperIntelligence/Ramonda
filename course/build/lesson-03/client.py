#!/usr/bin/env python3
"""Lesson 03: a thin client.

No model key. No tools. No history. It sends text and prints text.
"""

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8765"


def post(text: str) -> str:
    request = urllib.request.Request(
        BASE + "/send",
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)["reply"]


def history() -> list[dict]:
    with urllib.request.urlopen(BASE + "/history") as response:
        return json.load(response)["messages"]


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--history":
        for message in history():
            print(f"{message['role'].upper()}: {message['content']}\n")
        return
    if not args:
        sys.exit('usage: client.py "message" | client.py --history')
    print(post(" ".join(args)))


if __name__ == "__main__":
    main()
