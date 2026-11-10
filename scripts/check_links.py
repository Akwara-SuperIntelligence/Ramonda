"""Fail if a local Markdown or reference HTML link does not resolve."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
HTML = re.compile(r'href="([^"]+)"')
TARGETS = sorted(ROOT.glob("*.md"))
TARGETS += sorted((ROOT / "reference").glob("*.html"))
TARGETS += sorted((ROOT / "course").rglob("*.md"))
TARGETS += sorted((ROOT / "course").rglob("*.html"))


def check_sections(bad: list[str]) -> None:
    """A section reference must name a heading that exists.

    shortcut: in the root documents a section number always means EDA.md. Course
    files cite the source talk, not this repository, so they are not checked.
    """
    numbers = set(re.findall(r"^## (\d+)\.", (ROOT / "EDA.md").read_text(), re.M))
    for path in sorted(ROOT.glob("*.md")):
        for number in re.findall(r"§ ?(\d+)", path.read_text()):
            if number not in numbers:
                bad.append(f"{path.name}: section {number} has no heading in EDA.md")


def main() -> int:
    bad: list[str] = []
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
    check_sections(bad)
    print("\n".join(bad) if bad else "all local links resolve, all sections exist")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
