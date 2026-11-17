#!/bin/sh
# dev-only: demo Odoo logins from deploy/odoo/logins.json. Not production secrets.
set -eu
file=/logins.json
expected=$(grep -c '"login"' "$file")
tmp=$(mktemp)
sed -n 's/.*"login": "\([^"]*\)".*"password": "\([^"]*\)".*/\1 \2/p' "$file" > "$tmp"
got=0
while read -r login password; do
  [ -n "$login" ] || continue
  case $login in
    *[!A-Za-z0-9_-]*)
      echo "rejected login" >&2
      exit 1
      ;;
  esac
  case $password in
    ''|-*|*\"*|*[[:space:]]*)
      echo "rejected password" >&2
      exit 1
      ;;
  esac
  payload=$(mktemp)
  printf '{"login":"%s","password":"%s"}\n' "$login" "$password" > "$payload"
  if ! bao kv put -non-interactive "secret/odoo/$login" "@$payload" >/dev/null </dev/null; then
    rm -f "$payload"
    echo "openbao write failed" >&2
    exit 1
  fi
  rm -f "$payload"
  stored_login=$(bao kv get -non-interactive -field=login "secret/odoo/$login" </dev/null)
  stored_password=$(bao kv get -non-interactive -field=password "secret/odoo/$login" </dev/null)
  if [ "$stored_login" != "$login" ] || [ "$stored_password" != "$password" ]; then
    echo "openbao seed mismatch" >&2
    exit 1
  fi
  got=$((got + 1))
done < "$tmp"
rm -f "$tmp"
if [ "$got" -ne "$expected" ]; then
  echo "openbao seed count mismatch" >&2
  exit 1
fi
