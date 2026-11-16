#!/bin/sh
# shortcut: grep, not a parse; upgrade when a comment inside a string is a real false positive
# The gateway src tree is the hot path. Crate roots stay lib.rs or main.rs.
set -eu
unset CDPATH
cd -- "$(git rev-parse --show-toplevel)"

allow='//[!/]|/\*[!*]|noqa|type: *ignore|pyright:|pylint:|mypy:|biome-ignore|@ts-(ignore|expect-error|nocheck)|SPDX|Copyright|License|https?://'

bad_hot() {
	grep '^core/gateway/src/.*\.rs$' | grep -Ev '(^|/)(lib|main|mod)\.rs$|\.hot\.rs$' || true
}

bad_comments() {
	text=$(cat)
	shortcut=$(printf '%s\n' "$text" | grep -F 'shortcut:' || true)
	rest=$(printf '%s\n' "$text" | grep -Ev 'shortcut:' | grep -Eiv "$allow" || true)
	printf '%s\n%s\n' "$shortcut" "$rest" | sed '/^$/d'
}

got=$(printf '%s\n' \
	'core/gateway/src/lib.rs' \
	'core/gateway/src/read.rs' \
	'core/gateway/src/io.hot.rs' \
	'core/relay/src/lib.rs' | bad_hot)
[ "$got" = 'core/gateway/src/read.rs' ]
got=$(printf '%s\n' \
	'a.rs:1:// narrates' \
	'a.rs:2:/// docs' \
	'a.rs:3:// shortcut: later' \
	'a.py:4:# noqa: F401' \
	'a.rs:5:// https://example.com/limit' \
	'a.rs:6:/* waits */' | bad_comments)
[ "$got" = 'a.rs:3:// shortcut: later
a.rs:1:// narrates
a.rs:6:/* waits */' ]

status=0
hot=$(git ls-files '*.rs' | bad_hot)
if [ -n "$hot" ]; then
	printf '%s\n' "$hot" | sed 's/$/: name a hot-path file *.hot.rs. Fix the structure./' >&2
	status=1
fi
hits=$(git grep -n -I -E '(^|[^:])//|/\*|(^|[[:space:]])#[^![]' -- '*.rs' '*.py' '*.ts' '*.tsx' || true)
if [ -n "$hits" ]; then
	bad=$(printf '%s\n' "$hits" | bad_comments)
	if [ -n "$bad" ]; then
		printf '%s\n' "$bad" | sed 's/$/: make it a type, a lint, or a test./' >&2
		status=1
	fi
fi
exit "$status"
