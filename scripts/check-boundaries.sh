#!/usr/bin/env bash
# Fails when a module depends on a crate outside its allowed set (docs/system/modules.md).
# shortcut: greps manifests, not the resolved graph; upgrade if a transitive edge matters.
set -uo pipefail
fail=0
deps() { sed -n '/^\[dependencies/,$p' "crates/$1/Cargo.toml" 2>/dev/null; }
forbid() { # crate, regex, why
  if deps "$1" | grep -qE "$2"; then
    echo "error: crates/$1 must not depend on $2 - $3"
    fail=1
  fi
}
forbid rules    'ramonda-(case|corpus|agent|evidence|identity)' 'reverse edge: the engine takes values, not modules'
forbid evidence 'ramonda-'                                      'the ledger is a leaf'
forbid identity 'ramonda-'                                      'identity is a leaf'
forbid corpus   'ramonda-(case|agent)'                          'no upward edge'
forbid case     'ramonda-agent'                                 'no upward edge'
[ "$fail" = 0 ] && echo "boundaries ok"
exit $fail
