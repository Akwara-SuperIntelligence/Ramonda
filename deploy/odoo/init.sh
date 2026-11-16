#!/bin/bash
set -euo pipefail

DB="${ODOO_DATABASE:?}"
HOST="${HOST:?}"
PORT="${PORT:-5432}"
USER="${USER:?}"
export PGPASSWORD="${PASSWORD:?}"
[[ "$DB" =~ ^[A-Za-z0-9_]+$ ]]

python3 /usr/local/bin/wait-for-psql.py \
  --db_host "$HOST" --db_port "$PORT" --db_user "$USER" --db_password "$PASSWORD" --timeout=60

args=(--db_host "$HOST" --db_port "$PORT" --db_user "$USER" --db_password "$PASSWORD" -d "$DB" --without-demo=True)

count="$(psql -h "$HOST" -p "$PORT" -U "$USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB}'" || true)"
ready=0
if [[ "$count" == "1" ]]; then
  ready="$(psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -tAc "SELECT count(*) FROM ir_module_module WHERE name IN ('point_of_sale','stock') AND state = 'installed'" 2>/dev/null || true)"
fi
if [[ "$ready" != "2" ]]; then
  odoo "${args[@]}" --stop-after-init --init=point_of_sale,stock
fi

odoo shell "${args[@]}" --no-http --max-cron-threads=0 <<'PY'
import json
rows = json.load(open("/etc/odoo/logins.json"))
Users = env["res.users"].with_context(no_reset_password=True)
groups = env.ref("point_of_sale.group_pos_user") | env.ref("stock.group_stock_user")
for row in rows:
    if Users.search([("login", "=", row["login"])], limit=1):
        continue
    Users.create({
        "name": row["name"],
        "login": row["login"],
        "password": row["password"],
        "group_ids": [(6, 0, groups.ids)],
    })
missing = [row["login"] for row in rows if not Users.search([("login", "=", row["login"])], limit=1)]
if missing:
    raise SystemExit("missing odoo users")
env.cr.commit()
PY

ready="$(psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -tAc "SELECT count(*) FROM ir_module_module WHERE name IN ('point_of_sale','stock') AND state = 'installed'")"
[[ "$ready" == "2" ]]
exec odoo "${args[@]}"
