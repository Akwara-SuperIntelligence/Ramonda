#!/bin/sh
set -eu
unset CDPATH
cd -- "$(dirname -- "$0")"

mkdir -p target
tmp=$(mktemp -d "$PWD/target/crate-graph.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
tar --exclude=target --exclude=node_modules -cf - . | tar -C "$tmp" -xf -

meta=$(cd "$tmp" && cargo metadata --offline --format-version 1 --quiet --color never)
script=$(cat <<'PY'
import json
import sys

meta = json.load(sys.stdin)
packages = {package["id"]: package for package in meta["packages"]}
nodes = {node["id"]: node for node in meta["resolve"]["nodes"]}
members = set(meta["workspace_members"])
relays = [package_id for package_id in members if packages[package_id]["name"] == "relay"]
if len(relays) != 1:
    sys.stderr.write("crate-graph check: expected one workspace package named relay\n")
    sys.exit(1)
relay_id = relays[0]


def dev_only(dep):
    kinds = dep.get("dep_kinds") or []
    return bool(kinds) and all(kind.get("kind") == "dev" for kind in kinds)


if any(dep["name"] == "gateway" for dep in packages[relay_id]["dependencies"]):
    sys.stderr.write("relay depends on gateway. Use outbox.\n")
    sys.exit(1)

seen = set()
stack = [(relay_id, True)]
while stack:
    package_id, follow_dev = stack.pop()
    if package_id in seen:
        continue
    seen.add(package_id)
    if package_id != relay_id and packages[package_id]["name"] == "gateway":
        sys.stderr.write("relay depends on gateway. Use outbox.\n")
        sys.exit(1)
    node = nodes.get(package_id)
    if node is None:
        continue
    for dep in node["deps"]:
        if dev_only(dep) and not follow_dev:
            continue
        stack.append((dep["pkg"], False))
PY
)
printf '%s\n' "$meta" | python3 -c "$script"
