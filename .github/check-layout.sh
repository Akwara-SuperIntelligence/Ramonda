#!/bin/sh
set -eu
unset CDPATH
cd -- "$(git rev-parse --show-toplevel)"
exec python3 - "$@" <<'PY'
import ast
import json
import posixpath
import re
import subprocess
import sys

RUST_HOMES = ("core/gateway/", "core/relay/", "core/outbox/")
PYTHON_HOME = "connectors/"
PYTHON_EXCEPTION = "scripts/seed_akwara_cafe.py"
TYPESCRIPT_HOME = "core/console/"
CONFIG_ROOTS = ("packs/", "clients/")
CONFIG_MODULES = {"packs", "clients"}
MANIFESTS = {
    "Cargo.toml",
    "Pipfile",
    "package.json",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
}
PYTHON_SUFFIXES = (".py", ".pyi")
TYPESCRIPT_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")
SCRIPT_SUFFIXES = TYPESCRIPT_SUFFIXES + (".js", ".jsx", ".mjs", ".cjs")

TS_SPEC = re.compile(
    r"""(?:\bfrom\s+|\bimport\s*\(|\brequire\s*\(|\bimport\s+)(['"`])(.*?)\1""",
    re.DOTALL,
)
INCLUDE = re.compile(r'\binclude!\s*\(\s*"([^"]*)"')
PATH_ATTR = re.compile(r'#\[\s*path\s*=\s*"([^"]*)"\s*\]')
TOML_PATH = re.compile(r"""path\s*=\s*['"]([^'"]+)['"]""")
C_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def strip_c_comments(text: str) -> str:
    return C_COMMENT.sub("", text)


def strip_hash_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def top_module(name: str) -> str:
    return name.split(".", 1)[0]


def targets(spec: str, file_dir: str) -> bool:
    spec = spec.strip()
    for prefix in ("file:", "link:"):
        spec = spec.removeprefix(prefix)
    spec = spec.split("?", 1)[0].split("#", 1)[0]
    if spec in CONFIG_MODULES or spec.startswith(("packs/", "clients/")):
        return True
    if spec.startswith("."):
        norm = posixpath.normpath(posixpath.join(file_dir, spec))
        return norm in CONFIG_MODULES or norm.startswith(("packs/", "clients/"))
    return False


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def check_homes(files: list[str], errors: list[str]) -> None:
    for path in files:
        if path.endswith(".rs") and not path.startswith(RUST_HOMES):
            errors.append(
                f"{path}: Rust lives in core/gateway, core/relay, and core/outbox."
            )
        elif (
            path.endswith(PYTHON_SUFFIXES)
            and path != PYTHON_EXCEPTION
            and not path.startswith(PYTHON_HOME)
        ):
            errors.append(
                f"{path}: Python lives under connectors/. "
                "scripts/seed_akwara_cafe.py is the one other Python file."
            )
        elif path.endswith(TYPESCRIPT_SUFFIXES) and not path.startswith(
            TYPESCRIPT_HOME
        ):
            errors.append(f"{path}: TypeScript lives in core/console.")


def forbid(path: str, spec: str, errors: list[str]) -> None:
    errors.append(f"{path}: imports {spec}. Read the files as config.")


def check_py(path: str, errors: list[str]) -> None:
    try:
        tree = ast.parse(read(path), filename=path)
    except SyntaxError as err:
        errors.append(f"{path}: {err.msg}")
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if top_module(alias.name) in CONFIG_MODULES:
                    forbid(path, alias.name, errors)
        elif isinstance(node, ast.ImportFrom):
            if (
                node.level == 0
                and node.module
                and top_module(node.module) in CONFIG_MODULES
            ):
                forbid(path, node.module, errors)
        elif isinstance(node, ast.Call) and call_name(node.func) in {
            "import_module",
            "__import__",
        }:
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            value = node.args[0].value
            if isinstance(value, str) and top_module(value) in CONFIG_MODULES:
                forbid(path, value, errors)


def check_script(path: str, errors: list[str]) -> None:
    file_dir = posixpath.dirname(path)
    for _, spec in TS_SPEC.findall(strip_c_comments(read(path))):
        if targets(spec, file_dir):
            forbid(path, spec, errors)


def check_rs(path: str, errors: list[str]) -> None:
    text = strip_c_comments(read(path))
    file_dir = posixpath.dirname(path)
    for pattern in (INCLUDE, PATH_ATTR):
        for spec in pattern.findall(text):
            if targets(spec, file_dir):
                forbid(path, spec, errors)


def check_toml(path: str, errors: list[str]) -> None:
    file_dir = posixpath.dirname(path)
    for spec in TOML_PATH.findall(strip_hash_comments(read(path))):
        if targets(spec, file_dir):
            forbid(path, spec, errors)


def check_package_json(path: str, errors: list[str]) -> None:
    data = json.loads(read(path))
    if not isinstance(data, dict):
        return
    file_dir = posixpath.dirname(path)
    for field in (
        "dependencies",
        "devDependencies",
        "optionalDependencies",
        "peerDependencies",
    ):
        deps = data.get(field) or {}
        if not isinstance(deps, dict):
            continue
        for name, spec in deps.items():
            if name in CONFIG_MODULES or (
                isinstance(spec, str) and targets(spec, file_dir)
            ):
                forbid(path, name, errors)


def check_config(files: list[str], errors: list[str]) -> None:
    for path in files:
        if path.startswith(CONFIG_ROOTS) and posixpath.basename(path) in MANIFESTS:
            errors.append(
                f"{path}: packs/ and clients/ have no package manifest. "
                "Read the files as config."
            )
        if path.endswith(PYTHON_SUFFIXES):
            check_py(path, errors)
        elif path.endswith(SCRIPT_SUFFIXES):
            check_script(path, errors)
        elif path.endswith(".rs"):
            check_rs(path, errors)
        elif posixpath.basename(path) in {"Cargo.toml", "pyproject.toml"}:
            check_toml(path, errors)
        elif posixpath.basename(path) == "package.json":
            check_package_json(path, errors)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode not in {"all", "homes", "config"}:
        sys.stderr.write("usage: check-layout.sh [homes|config]\n")
        sys.exit(2)
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    files = [item.decode() for item in raw.split(b"\0") if item]
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
