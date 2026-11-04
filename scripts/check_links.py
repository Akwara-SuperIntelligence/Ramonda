"""Fail if a local Markdown or reference HTML link does not resolve."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
HTML = re.compile(r'href="([^"]+)"')
TARGETS = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "GLOSSARY.md"]
TARGETS += sorted((ROOT / "docs").rglob("*.md"))
TARGETS += sorted((ROOT / "services").rglob("*.md"))
TARGETS += sorted((ROOT / "reference").glob("*.html"))


def main() -> int:
    bad = []
    for path in TARGETS:
        if any(part.startswith(".") for part in path.relative_to(ROOT).parts):
            continue
        links = MARKDOWN if path.suffix == ".md" else HTML
        for match in links.findall(path.read_text()):
            target = match.strip().strip("<>").split("#")[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (path.parent / target).resolve().exists():
                bad.append(f"{path.relative_to(ROOT)}: {target}")
    print("\n".join(bad) if bad else "all local links resolve")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
