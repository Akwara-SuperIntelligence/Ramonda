#!/bin/sh
# shortcut: line scan, not a parser; upgrade when a string or nested comment is a real false positive
set -eu
unset CDPATH
cd -- "$(git rev-parse --show-toplevel)"
exec python3 - "$@" <<'PY'
import posixpath
import re
import subprocess
import sys

MESSAGE = "make it a type, a lint, or a test."
SHORTCUT = "shortcut:"
LINK = re.compile(r"https?://")
LICENSE = re.compile(r"spdx-license-identifier|\blicense\b|\bcopyright\b", re.I)
RUST_PUB = re.compile(
    r"^pub\s+(?:(?:async|unsafe|const)\s+|extern(?:\s+\"[^\"]*\")?\s+)*"
    r"(?:fn|struct|enum|trait|type|const|static|mod|use|union)\b"
)
PY_DEF = re.compile(r"^(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\b")
TS_EXPORT = re.compile(r"^export\b")
KINDS = {
    "all": (".rs", ".py", ".ts", ".tsx"),
    "rust": (".rs",),
    "python": (".py",),
    "typescript": (".ts", ".tsx"),
}


def tracked() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    return [item.decode() for item in raw.split(b"\0") if item]


def read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def fail(errors: list[str], path: str, lineno: int) -> None:
    errors.append(f"{path}:{lineno}: {MESSAGE}")


def allowed_text(text: str, header: bool, public_doc: bool) -> bool:
    if SHORTCUT in text:
        return False
    if public_doc or LINK.search(text):
        return True
    return bool(header and LICENSE.search(text))


def split_hash(line: str) -> tuple[str, str | None]:
    stripped = line.strip()
    if stripped.startswith("#"):
        return "", stripped[1:]
    mark = line.find(" #")
    if mark == -1:
        return line, None
    return line[:mark], line[mark + 2 :]


def consume_string(lines: list[str], start: int) -> tuple[int, str]:
    stripped = lines[start].strip()
    quote = '"""' if stripped.startswith('"""') else "'''"
    block = [lines[start]]
    if stripped.count(quote) >= 2:
        return start, "\n".join(block)
    index = start + 1
    while index < len(lines):
        block.append(lines[index])
        if quote in lines[index]:
            return index, "\n".join(block)
        index += 1
    return len(lines) - 1, "\n".join(block)


def check_python(path: str, text: str, errors: list[str]) -> None:
    lines = text.splitlines()
    header = True
    index = 0
    while index < len(lines):
        line = lines[index]
        lineno = index + 1
        stripped = line.strip()
        if stripped == "":
            index += 1
            continue
        if lineno == 1 and line.startswith("#!"):
            index += 1
            continue
        if stripped.startswith(('"""', "'''")):
            end, block = consume_string(lines, index)
            if not allowed_text(block, header, False):
                fail(errors, path, lineno)
            header = False
            index = end + 1
            continue
        code, comment = split_hash(line)
        if comment is not None and code.strip() == "":
            if not allowed_text(comment, header, False):
                fail(errors, path, lineno)
            index += 1
            continue
        if comment is not None and not allowed_text(comment, False, False):
            fail(errors, path, lineno)
        code_stripped = code.strip()
        if code_stripped == "":
            index += 1
            continue
        header = False
        match = PY_DEF.match(code_stripped)
        if not match:
            index += 1
            continue
        public = not match.group(1).startswith("_")
        signature = code_stripped
        while not signature.endswith(":"):
            index += 1
            if index >= len(lines):
                return
            part, part_comment = split_hash(lines[index])
            if part_comment is not None and not allowed_text(part_comment, False, False):
                fail(errors, path, index + 1)
            signature = part.strip()
        next_index = index + 1
        while next_index < len(lines) and lines[next_index].strip() == "":
            next_index += 1
        if next_index < len(lines) and lines[next_index].strip().startswith(('"""', "'''")):
            end, block = consume_string(lines, next_index)
            if not allowed_text(block, False, public):
                fail(errors, path, next_index + 1)
            index = end + 1
            continue
        index += 1


def pieces(text: str) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    block: str | None = None
    for lineno, line in enumerate(text.splitlines(), 1):
        if block is not None:
            end = line.find("*/")
            if end == -1:
                found.append((lineno, block, line))
                continue
            found.append((lineno, block, line[:end]))
            block = None
            line = line[end + 2 :]
        start = 0
        index = 0
        while index < len(line):
            if line.startswith("/*", index):
                if index > start:
                    found.append((lineno, "code", line[start:index]))
                if line.startswith("/**", index) and not line.startswith(("/***", "/**/"), index):
                    kind = "doc"
                    mark = index + 3
                elif line.startswith("/*!", index):
                    kind = "inner"
                    mark = index + 3
                else:
                    kind = "comment"
                    mark = index + 2
                end = line.find("*/", mark)
                if end == -1:
                    found.append((lineno, kind, line[mark:]))
                    block = kind
                    start = len(line)
                    break
                found.append((lineno, kind, line[mark:end]))
                index = end + 2
                start = index
                continue
            if line.startswith("//", index) and (index == 0 or line[index - 1] != ":"):
                if index > start:
                    found.append((lineno, "code", line[start:index]))
                if line.startswith("///", index):
                    found.append((lineno, "doc", line[index + 3 :]))
                elif line.startswith("//!", index):
                    found.append((lineno, "inner", line[index + 3 :]))
                else:
                    found.append((lineno, "comment", line[index + 2 :]))
                start = len(line)
                break
            index += 1
        else:
            if start < len(line):
                found.append((lineno, "code", line[start:]))
    return found


def check_code(path: str, text: str, lang: str, errors: list[str]) -> None:
    header = True
    bracket = 0
    pending: list[tuple[int, str]] = []
    name = posixpath.basename(path)

    def emit(lineno: int, comment: str, public_doc: bool) -> None:
        if not allowed_text(comment, header, public_doc):
            fail(errors, path, lineno)

    def flush(public_doc: bool) -> None:
        for lineno, comment in pending:
            emit(lineno, comment, public_doc)
        pending.clear()

    for lineno, kind, comment in pieces(text):
        if kind == "doc":
            pending.append((lineno, comment))
            continue
        if kind == "inner":
            flush(False)
            emit(lineno, comment, header and name in {"lib.rs", "main.rs"})
            continue
        if kind == "comment":
            flush(False)
            emit(lineno, comment, False)
            continue
        stripped = comment.strip()
        if stripped == "":
            continue
        if bracket == 0 and stripped.startswith(("#[", "#![")):
            bracket = max(0, stripped.count("[") - stripped.count("]"))
            header = False
            continue
        if bracket > 0:
            bracket = max(0, bracket + stripped.count("[") - stripped.count("]"))
            continue
        if lang == "ts" and stripped.startswith("@"):
            continue
        public = bool(RUST_PUB.match(stripped) if lang == "rust" else TS_EXPORT.match(stripped))
        flush(public)
        header = False
    flush(False)


def main() -> None:
    kind = sys.argv[1] if len(sys.argv) > 1 else "all"
    suffixes = KINDS.get(kind)
    if suffixes is None:
        sys.stderr.write("usage: check-comments.sh [rust|python|typescript]\n")
        sys.exit(2)
    errors: list[str] = []
    for path in tracked():
        if not path.endswith(suffixes):
            continue
        text = read(path)
        if path.endswith(".py"):
            check_python(path, text, errors)
        elif path.endswith(".rs"):
            check_code(path, text, "rust", errors)
        else:
            check_code(path, text, "ts", errors)
    if errors:
        sys.stderr.write("\n".join(errors) + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
PY
