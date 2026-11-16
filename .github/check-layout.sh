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
PATH_ATTR = re.compile(r'#\[\s*path\s*=\s*"([^"]*)"\s*\]')
TOML_PATH = re.compile(r"""path\s*=\s*['"]([^'"]+)['"]""")
C_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
INCLUDE_PAIRS = {"(": ")", "[": "]", "{": "}"}


def read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def strip_c_comments(text: str) -> str:
    return C_COMMENT.sub("", text)


def at_boundary(text: str, index: int) -> bool:
    return index == 0 or not (text[index - 1].isalnum() or text[index - 1] == "_")


def read_raw(text: str, index: int) -> tuple[int, str] | None:
    if not at_boundary(text, index):
        return None
    matched = re.match(r'(?:br|cr|r)(#*)"', text[index:])
    if not matched:
        return None
    hashes = matched.group(1)
    start = index + matched.end()
    end = text.find('"' + hashes, start)
    if end == -1:
        return len(text), text[start:]
    return end + len(hashes) + 1, text[start:end]


def read_cooked(text: str, index: int) -> tuple[int, str] | None:
    if text[index] == '"':
        cursor = index + 1
    elif text.startswith(('b"', 'c"'), index) and at_boundary(text, index):
        cursor = index + 2
    else:
        return None
    chars: list[str] = []
    while cursor < len(text):
        if text[cursor] == "\\":
            if cursor + 1 < len(text):
                chars.append(text[cursor + 1])
            cursor += 2
            continue
        if text[cursor] == '"':
            return cursor + 1, "".join(chars)
        if text[cursor] == "\n":
            return None
        chars.append(text[cursor])
        cursor += 1
    return None


def try_char(text: str, index: int) -> int | None:
    if not at_boundary(text, index):
        return None
    matched = re.match(r"b?'", text[index:])
    if not matched:
        return None
    cursor = index + matched.end()
    if cursor >= len(text):
        return None
    if text[cursor] == "\\":
        if text.startswith("\\u{", cursor):
            end = text.find("}", cursor)
            if end == -1:
                return None
            cursor = end + 1
        else:
            cursor += 2
    else:
        cursor += 1
    if cursor < len(text) and text[cursor] == "'":
        return cursor + 1
    return None


def skip_block(text: str, index: int) -> int:
    depth = 1
    while index < len(text) and depth:
        if text.startswith("/*", index):
            depth += 1
            index += 2
        elif text.startswith("*/", index):
            depth -= 1
            index += 2
        else:
            index += 1
    return index


def strip_rust(text: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        literal = read_raw(text, index) or read_cooked(text, index)
        if literal is not None:
            out.append(text[index : literal[0]])
            index = literal[0]
            continue
        end = try_char(text, index)
        if end is not None:
            out.append(text[index:end])
            index = end
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index)
            index = len(text) if newline == -1 else newline
            continue
        if text.startswith("/*", index):
            index = skip_block(text, index + 2)
            continue
        out.append(text[index])
        index += 1
    return "".join(out)


def parse_include(text: str, index: int) -> tuple[list[str], int]:
    length = len(text)
    while index < length and text[index].isspace():
        index += 1
    if index >= length or text[index] not in INCLUDE_PAIRS:
        return [], index
    closer = INCLUDE_PAIRS[text[index]]
    index += 1
    while index < length and text[index].isspace():
        index += 1
    literal = read_raw(text, index) or read_cooked(text, index)
    if literal is None:
        return [], index
    end, content = literal
    cursor = end
    while cursor < length and text[cursor].isspace():
        cursor += 1
    if cursor < length and text[cursor] == closer:
        return [content], cursor + 1
    return [], end


def include_paths(text: str) -> list[str]:
    paths: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text.startswith("//", index):
            newline = text.find("\n", index)
            index = length if newline == -1 else newline + 1
            continue
        if text.startswith("/*", index):
            index = skip_block(text, index + 2)
            continue
        if at_boundary(text, index) and text.startswith("include!", index):
            found, index = parse_include(text, index + len("include!"))
            paths.extend(found)
            continue
        literal = read_raw(text, index) or read_cooked(text, index)
        if literal is not None:
            index = literal[0]
            continue
        end = try_char(text, index)
        if end is not None:
            index = end
            continue
        index += 1
    return paths


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
        return filesystem_targets(spec, file_dir)
    return False


def filesystem_targets(spec: str, file_dir: str) -> bool:
    spec = spec.strip()
    if not spec or spec.startswith("/"):
        return False
    norm = posixpath.normpath(posixpath.join(file_dir, spec))
    return norm in CONFIG_MODULES or norm.startswith(("packs/", "clients/"))


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


def dynamic_names(tree: ast.AST) -> set[str]:
    names = {"import_module", "__import__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "import_module":
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported = alias.name.rsplit(".", 1)[-1]
                if imported == "import_module" and alias.asname:
                    names.add(alias.asname)
    return names


def called_modules(tree: ast.AST) -> list[str]:
    names = dynamic_names(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or call_name(node.func) not in names:
            continue
        value = module_argument(node)
        if value is not None:
            found.append(value)
    return found


def module_argument(node: ast.Call) -> str | None:
    if node.args:
        value = node.args[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
        return None
    for keyword in node.keywords:
        if keyword.arg != "name" or not isinstance(keyword.value, ast.Constant):
            continue
        if isinstance(keyword.value.value, str):
            return keyword.value.value
    return None


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
        elif isinstance(node, ast.ImportFrom) and (
            node.level == 0
            and node.module
            and top_module(node.module) in CONFIG_MODULES
        ):
            forbid(path, node.module, errors)
    for value in called_modules(tree):
        if top_module(value) in CONFIG_MODULES:
            forbid(path, value, errors)


def check_script(path: str, errors: list[str]) -> None:
    file_dir = posixpath.dirname(path)
    for _, spec in TS_SPEC.findall(strip_c_comments(read(path))):
        if targets(spec, file_dir):
            forbid(path, spec, errors)


def check_rs(path: str, errors: list[str]) -> None:
    text = read(path)
    file_dir = posixpath.dirname(path)
    specs = include_paths(text)
    specs.extend(PATH_ATTR.findall(strip_rust(text)))
    for spec in specs:
        if filesystem_targets(spec, file_dir):
            forbid(path, spec, errors)


def check_toml(path: str, errors: list[str]) -> None:
    file_dir = posixpath.dirname(path)
    for spec in TOML_PATH.findall(strip_hash_comments(read(path))):
        if filesystem_targets(spec, file_dir):
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


def self_check() -> None:
    hidden = (
        'pub const OPEN: &str = "/*";\n'
        'include!("../../../packs/rules.inc");\n'
        'pub const CLOSE: &str = "*/";\n'
    )
    commented = '/* include!("../../../packs/rules.inc"); */\n'
    braced = 'include! { "../../../packs/rules.inc" }\n'
    bracketed = 'include!["../../../packs/rules.inc"]\n'
    literal = 'include_str!("../../../packs/hospitality/x.toml");\n'
    raw_include = 'include!(r"../../../packs/rules.inc");\n'
    raw_text = 'const EXAMPLE: &str = r#"include!("../../../packs/rules.inc");"#;\n'
    alias = 'from importlib import import_module as load\nload("packs")\n'
    keyword = 'from importlib import import_module as load\nload(name="packs")\n'
    ok = (
        "../../../packs/rules.inc" in include_paths(hidden)
        and not include_paths(commented)
        and "../../../packs/rules.inc" in include_paths(braced)
        and "../../../packs/rules.inc" in include_paths(bracketed)
        and not include_paths(literal)
        and "../../../packs/rules.inc" in include_paths(raw_include)
        and not include_paths(raw_text)
        and filesystem_targets("local/../../../../packs/rules.inc", "core/gateway/src")
        and "packs" in called_modules(ast.parse(alias))
        and "packs" in called_modules(ast.parse(keyword))
    )
    if not ok:
        sys.stderr.write("layout self-check failed\n")
        sys.exit(1)


def main() -> None:
    self_check()
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
