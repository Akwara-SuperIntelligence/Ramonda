#!/usr/bin/env python3
"""Lesson 07: seed a profile and one dated log.

    .venv/bin/python build/lesson-07/seed.py
"""

from datetime import date, timedelta
from pathlib import Path

MEMORY = Path(__file__).resolve().parents[1] / "lesson-03" / "memory"
PROFILE = MEMORY / "profile.md"
LOGS = MEMORY / "log"

MEMORY.mkdir(parents=True, exist_ok=True)
PROFILE.write_text(
    "# Profile\n"
    "- Works on a personal always-on agent in Python.\n"
    "- Prefers short, direct explanations.\n"
    "- Timezone: Africa/Nairobi.\n"
)

yesterday = date.today() - timedelta(days=1)
log = LOGS / f"{yesterday.isoformat()}.md"
log.parent.mkdir(parents=True, exist_ok=True)
log.write_text(
    f"# {yesterday.isoformat()}\n\n"
    "## 14:20\n"
    "USER: Run the log analysis on big.log.\n"
    "AGENT: The log analysis found 6000 lines: INFO 3622, WARN 1173, ERROR 1205. "
    "Top errors: database timeout, payment declined, rate limit exceeded.\n"
)

print(f"wrote {PROFILE}")
print(f"wrote {log}")
