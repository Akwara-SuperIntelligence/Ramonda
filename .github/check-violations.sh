#!/bin/sh
set -eu
unset CDPATH
cd -- "$(git rev-parse --show-toplevel)"

mode=${1:-}
case "$mode" in
    comments|comments-ok|boundary|hot) ;;
    *)
        echo "usage: check-violations.sh comments|comments-ok|boundary|hot" >&2
        exit 2
        ;;
esac

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/repo"
tar --exclude=target --exclude=node_modules --exclude=.venv -cf - . | tar -C "$work/repo" -xf -

python3 - "$work/repo" "$mode" <<'PY'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
mode = sys.argv[2]

def write(path, text):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text)

if mode == "comments":
    write(
        "core/gateway/src/lib.rs",
        """\
/// Hidden.
fn hidden() {}

/// Crate only.
pub(crate) fn inside() {}

// The gateway waits here.

/* waits */

// shortcut: no buffer yet, add one when the socket lands
""",
    )
    write(
        "connectors/odoo/src/odoo/server.py",
        """\
\"\"\"This module narrates.\"\"\"

from mcp.server import MCPServer

mcp = MCPServer("odoo")


def _hidden():
    \"\"\"Private note.\"\"\"


class Cafe:
    \"\"\"Narrates the class.\"\"\"


# Then filter the rows.

# shortcut: skip the parser, when a string false-positive shows up
""",
    )
    write(
        "core/console/src/main.ts",
        """\
export {};

// Boot the console.

/** Not exported. */
function boot(): void {}

// shortcut: paint later, when the console has a screen
""",
    )
elif mode == "comments-ok":
    write(
        "core/gateway/src/lib.rs",
        """\
// SPDX-License-Identifier: Apache-2.0

//! Gateway.

/// Entry.
#[must_use]
pub struct Gateway;

/**
 * Starts the gateway.
 */
#[cfg(any(
    unix,
    windows,
))]
pub fn start() {}

// https://doc.rust-lang.org/std/
""",
    )
    write(
        "connectors/odoo/src/odoo/server.py",
        """\
#!/usr/bin/env python3
# Copyright Ramonda.

from mcp.server import MCPServer

mcp = MCPServer("odoo")


def read_sales():
    \"\"\"Westlands sales.\"\"\"
    return None


def read_branch(
    branch: str,
) -> str:
    \"\"\"Sales for one branch.\"\"\"
    return branch


# https://example.com/odoo
""",
    )
    write(
        "core/console/src/main.ts",
        """\
// SPDX-License-Identifier: Apache-2.0

/** Console entry. */
export function main(): void {}

/**
 * Builds the shell.
 */
export const shell = 1;

// https://example.com/console
""",
    )
elif mode == "boundary":
    path = root / "core/relay/Cargo.toml"
    path.write_text(path.read_text() + '\n[dependencies]\ngateway = { path = "../gateway" }\n')
elif mode == "hot":
    write(
        "core/gateway/src/lib.rs",
        """\
pub fn nap() {
    std::thread::sleep(std::time::Duration::from_millis(1));
}

#[path = "wait.hot.rs"]
pub mod wait;
""",
    )
    write(
        "core/gateway/src/wait.hot.rs",
        """\
pub fn wait() {
    std::thread::sleep(std::time::Duration::from_millis(1));
}
""",
    )
PY

cd "$work/repo"
out="$work/out"
case "$mode" in
    comments)
        set +e
        ./.github/check-comments.sh >"$out" 2>&1
        status=$?
        set -e
        if [ "$status" -eq 0 ]; then
            echo "narrating comments were allowed" >&2
            cat "$out" >&2
            exit 1
        fi
        python3 - "$out" <<'PY'
import sys

text = open(sys.argv[1], encoding="utf-8").read()
needle = "make it a type, a lint, or a test."
counts = {
    "core/gateway/src/lib.rs": 5,
    "connectors/odoo/src/odoo/server.py": 5,
    "core/console/src/main.ts": 3,
}
if needle not in text:
    sys.stderr.write(f"missing error text\n{text}")
    sys.exit(1)
for path, count in counts.items():
    found = text.count(path + ":")
    if found != count:
        sys.stderr.write(f"{path}: expected {count} violations, found {found}\n{text}")
        sys.exit(1)
PY
        ;;
    comments-ok)
        ./.github/check-comments.sh
        ;;
    boundary)
        set +e
        ./core/check-crate-graph.sh >"$out" 2>&1
        status=$?
        set -e
        if [ "$status" -eq 0 ] || ! grep -F "relay depends on gateway. Use outbox." "$out" >/dev/null; then
            echo "crate-graph did not reject relay depending on gateway" >&2
            cat "$out" >&2
            exit 1
        fi
        ;;
    hot)
        set +e
        ./.github/check-clippy.sh >"$out" 2>&1
        status=$?
        set -e
        if [ "$status" -eq 0 ] || ! grep -F "fix the structure" "$out" >/dev/null || ! grep -F "wait.hot.rs" "$out" >/dev/null; then
            echo "clippy did not reject the hot-path API" >&2
            cat "$out" >&2
            exit 1
        fi
        if grep -F -- "--> src/lib.rs" "$out" >/dev/null; then
            echo "denied API was rejected outside a hot file" >&2
            cat "$out" >&2
            exit 1
        fi
        ;;
esac
