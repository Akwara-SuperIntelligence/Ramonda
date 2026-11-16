#!/bin/sh
set -eu
unset CDPATH
cd -- "$(git rev-parse --show-toplevel)"
exec python3 - "$@" <<'PY'
import posixpath
import re
import subprocess
import sys

RUST_HOMES = ("core/gateway/", "core/relay/", "core/outbox/")
PYTHON_HOME = "connectors/"
PYTHON_EXCEPTION = "scripts/seed_akwara_cafe.py"
TYPESCRIPT_HOME = "core/console/"
CONFIG_ROOTS = ("packs/", "clients/")
REFERENCES = ("packs/", "clients/")
IMPORT_REF = re.compile(
    r"""\b(?:import|from)\s+['\"]?[^'\"\n]*(?:packs|clients)(?:\b|/)"""
)
MANIFESTS = {
    "Cargo.toml",
    "Pipfile",
    "package.json",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
}
CODE_SUFFIXES = (".py", ".rs", ".toml", ".ts", ".tsx")
CODE_NAMES = {"Cargo.toml", "package.json", "pyproject.toml"}


def tracked() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    return [item.decode() for item in raw.split(b"\0") if item]


def read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def check_homes(files: list[str], errors: list[str]) -> None:
    for path in files:
        if path.endswith(".rs") and not path.startswith(RUST_HOMES):
            errors.append(
                f"{path}: Rust lives in core/gateway, core/relay, and core/outbox."
            )
        elif (
            path.endswith(".py")
            and path != PYTHON_EXCEPTION
            and not path.startswith(PYTHON_HOME)
        ):
            errors.append(
                f"{path}: Python lives under connectors/. "
                "scripts/seed_akwara_cafe.py is the one other Python file."
            )
        elif path.endswith((".ts", ".tsx")) and not path.startswith(TYPESCRIPT_HOME):
            errors.append(f"{path}: TypeScript lives in core/console.")


def is_code(path: str) -> bool:
    return path.endswith(CODE_SUFFIXES) or posixpath.basename(path) in CODE_NAMES


def check_config(files: list[str], errors: list[str]) -> None:
    for path in files:
        if path.startswith(CONFIG_ROOTS) and posixpath.basename(path) in MANIFESTS:
            errors.append(
                f"{path}: packs/ and clients/ have no package manifest. "
                "Read the files as config."
            )
        if path.startswith(CONFIG_ROOTS) or not is_code(path):
            continue
        text = read(path)
        if posixpath.basename(path) in CODE_NAMES:
            for needle in REFERENCES:
                if needle in text:
                    errors.append(
                        f"{path}: refers to {needle}. Read the files as config."
                    )
            continue
        if IMPORT_REF.search(text):
            errors.append(
                f"{path}: imports packs or clients. Read the files as config."
            )


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode not in {"all", "homes", "config"}:
        sys.stderr.write("usage: check-layout.sh [homes|config]\n")
        sys.exit(2)
    files = tracked()
    errors: list[str] = []
    if mode in {"all", "homes"}:
        check_homes(files, errors)
    if mode in {"all", "config"}:
        check_config(files, errors)
    if errors:
        sys.stderr.write("\n".join(errors) + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
PY
