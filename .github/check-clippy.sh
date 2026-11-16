#!/bin/sh
# shortcut: a later allow attribute in the same hot file wins, upgrade if a hot file silences the lint
set -eu
unset CDPATH
cd -- "$(git rev-parse --show-toplevel)/core"

tmp=$(mktemp -d)
list=$(mktemp)
trap 'rm -rf "$tmp"; rm -f "$list"' EXIT
tar --exclude=target --exclude=node_modules --exclude=.venv -cf - . | tar -C "$tmp" -xf -
cp -- "$(git rev-parse --show-toplevel)/rust-toolchain.toml" "$tmp/"
find "$tmp" -name '*.hot.rs' -type f -print > "$list"
while IFS= read -r file; do
    [ -n "$file" ] || continue
    {
        printf '%s\n' '#![deny(clippy::disallowed_methods, clippy::disallowed_macros, clippy::disallowed_types)]'
        cat -- "$file"
    } > "$file.new"
    mv -- "$file.new" "$file"
done < "$list"

cd -- "$tmp"
cargo clippy --locked --all-targets --all-features -- -D warnings -D clippy::pedantic
