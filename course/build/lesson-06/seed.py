#!/usr/bin/env python3
"""Lesson 06: make a log big enough that reading it all would hurt.

    .venv/bin/python build/lesson-06/seed.py
"""

import random
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1] / "lesson-03" / "workspace"
LEVELS = ["INFO", "INFO", "INFO", "WARN", "ERROR"]
MESSAGES = {
    "INFO": ["request served", "cache hit", "user login", "job started", "job finished"],
    "WARN": ["slow query", "retry scheduled", "queue depth high", "token near limit"],
    "ERROR": [
        "payment declined",
        "database timeout",
        "invalid signature",
        "rate limit exceeded",
        "file not found",
    ],
}

random.seed(7)
lines = []
for i in range(6000):
    level = random.choice(LEVELS)
    message = random.choice(MESSAGES[level])
    lines.append(f"2026-10-{random.randint(1, 28):02d}T{random.randint(0, 23):02d}:{random.randint(0, 59):02d}:{random.randint(0, 59):02d}Z {level} {message} id={i}")

WORKSPACE.mkdir(parents=True, exist_ok=True)
target = WORKSPACE / "big.log"
target.write_text("\n".join(lines) + "\n")
print(f"wrote {target} ({target.stat().st_size} bytes, {len(lines)} lines)")
