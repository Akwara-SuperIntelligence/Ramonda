import json
import os
from datetime import date, timedelta
from typing import Any, cast
from urllib import request

REFERENCE = "akwara-seed"
BRANCH = "Westlands"
PRODUCT = "Butter croissant"
END = date(2026, 11, 16)
START = END - timedelta(days=55)
EARLY = (74, 76, 73, 75, 72)
LATE = (58, 60, 57, 59, 56)
WEEKEND_SOLD = 30
WEEKEND_DELIVERED = 40
WEEKDAY_DELIVERED = 80

WIPE_ORDERS = """
orders = env["pos.order"].search([("pos_reference", "=", "akwara-seed")])
if orders:
    env.cr.execute("UPDATE pos_order SET state = 'cancel' WHERE pos_reference = 'akwara-seed'")
    orders.invalidate_recordset(["state"])
    orders.unlink()
"""


def _week(day: date) -> int:
    return int((day - START).days / 7)


def days() -> list[tuple[date, int, int]]:
    rows: list[tuple[date, int, int]] = []
    day = START
    while day <= END:
        week = _week(day)
        if day.weekday() >= 5:
            rows.append((day, WEEKEND_SOLD, WEEKEND_DELIVERED))
        else:
            pattern = EARLY if week < 5 else LATE
            rows.append((day, pattern[day.weekday()], WEEKDAY_DELIVERED))
        day += timedelta(days=1)
    return rows


def _check(rows: list[tuple[date, int, int]]) -> None:
    early = [sold for day, sold, _delivered in rows if _week(day) < 5 and day.weekday() < 5]
    late = [sold for day, sold, _delivered in rows if _week(day) >= 5 and day.weekday() < 5]
    assert rows[0][0] == date(2026, 9, 22) and rows[-1][0] == END and rows[-1][0].weekday() == 0
    assert len(rows) == 56 and len(early) == 25 and len(late) == 15
    assert sum(early) == 74 * len(early) and sum(late) == 58 * len(late)
    assert all(delivered == WEEKDAY_DELIVERED for day, _sold, delivered in rows if day.weekday() < 5)
    assert all(
        sold < min(LATE) and delivered < WEEKDAY_DELIVERED
        for day, sold, delivered in rows
        if day.weekday() >= 5
    )


_check(days())


class Odoo:
    def __init__(self, url: str, database: str, login: str, password: str) -> None:
        self._url = url
        self._database = database
        self._password = password
        uid = self._rpc("common", "authenticate", [database, login, password, {}])
        if type(uid) is not int:
            raise SystemExit("Odoo authentication failed")
        self.uid = uid

    def execute(self, model: str, method: str, args: list[Any]) -> Any:
        return self._rpc(
            "object",
            "execute_kw",
            [self._database, self.uid, self._password, model, method, args, {}],
        )

    def _rpc(self, service: str, method: str, args: list[Any]) -> Any:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": 1,
        }
        req = request.Request(
            self._url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=120) as response:
            parsed: Any = json.loads(response.read())
        if not isinstance(parsed, dict):
            raise SystemExit("Odoo call failed")
        body = cast(dict[str, Any], parsed)
        if body.get("error") is not None or "result" not in body:
            raise SystemExit(_failure(body))
        return body["result"]


def _failure(body: dict[str, Any]) -> str:
    error = body.get("error")
    if isinstance(error, dict):
        data = cast(dict[str, Any], error).get("data")
        if isinstance(data, dict):
            message = cast(dict[str, Any], data).get("message")
            if isinstance(message, str) and message:
                return message
    return "Odoo call failed"


def _ids(value: object) -> list[int]:
    if not isinstance(value, list):
        raise SystemExit("Odoo call failed")
    found: list[int] = []
    for item in cast(list[object], value):
        if type(item) is not int:
            raise SystemExit("Odoo call failed")
        found.append(item)
    return found


def _one(value: object) -> dict[str, Any]:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return cast(dict[str, Any], value[0])
    raise SystemExit("Odoo call failed")


def _record(value: object) -> int:
    if type(value) is int:
        return value
    raise SystemExit("Odoo call failed")


def _link(row: dict[str, Any], field: str) -> int:
    value = row.get(field)
    if isinstance(value, list):
        items = cast(list[object], value)
        if items and type(items[0]) is int:
            return items[0]
    raise SystemExit("Odoo call failed")


def _find_or_create(odoo: Odoo, model: str, domain: list[list[Any]], vals: dict[str, Any]) -> int:
    found = _ids(odoo.execute(model, "search", [domain]))
    if found:
        return found[0]
    return _record(odoo.execute(model, "create", [vals]))


def _wipe(odoo: Odoo) -> None:
    moves = _ids(odoo.execute("stock.move", "search", [[["origin", "=", REFERENCE]]]))
    if moves:
        odoo.execute("stock.move", "write", [moves, {"state": "draft"}])
        odoo.execute("stock.move", "unlink", [moves])
    orders = _ids(odoo.execute("pos.order", "search", [[["pos_reference", "=", REFERENCE]]]))
    if not orders:
        return
    model = _ids(odoo.execute("ir.model", "search", [[["model", "=", "pos.order"]]]))
    action = _record(
        odoo.execute(
            "ir.actions.server",
            "create",
            [{"name": REFERENCE, "model_id": model[0], "state": "code", "code": WIPE_ORDERS}],
        )
    )
    try:
        odoo.execute("ir.actions.server", "run", [[action]])
    finally:
        odoo.execute("ir.actions.server", "unlink", [[action]])


def _load(odoo: Odoo, rows: list[tuple[date, int, int]]) -> None:
    uom = _ids(odoo.execute("uom.uom", "search", [[["name", "=", "Units"]]]))[0]
    product = _find_or_create(
        odoo,
        "product.product",
        [["name", "=", PRODUCT]],
        {"name": PRODUCT, "type": "consu", "is_storable": True, "uom_id": uom},
    )
    warehouse = _find_or_create(
        odoo,
        "stock.warehouse",
        [["name", "=", BRANCH]],
        {"name": BRANCH, "code": "WL"},
    )
    stock = _one(odoo.execute("stock.warehouse", "read", [[warehouse], ["lot_stock_id", "out_type_id"]]))
    config = _find_or_create(
        odoo,
        "pos.config",
        [["name", "=", BRANCH]],
        {"name": BRANCH, "picking_type_id": _link(stock, "out_type_id")},
    )
    session = _session(odoo, config)
    source = _ids(odoo.execute("stock.location", "search", [[["usage", "=", "inventory"]]]))[0]
    dest = _link(stock, "lot_stock_id")
    quants = _ids(
        odoo.execute(
            "stock.quant",
            "search",
            [[["product_id", "=", product], ["location_id", "in", [source, dest]]]],
        )
    )
    if quants:
        odoo.execute("stock.quant", "write", [quants, {"quantity": 0}])
    odoo.execute("pos.order", "create", [[_order(session, product, day, sold) for day, sold, _delivered in rows]])
    odoo.execute(
        "stock.move",
        "create",
        [[_move(product, uom, source, dest, day, delivered) for day, _sold, delivered in rows]],
    )


def _session(odoo: Odoo, config: int) -> int:
    found = _ids(
        odoo.execute(
            "pos.session",
            "search",
            [[["config_id", "=", config], ["state", "in", ["opening_control", "opened"]]]],
        )
    )
    session = found[0] if found else _record(
        odoo.execute("pos.session", "create", [{"config_id": config, "user_id": odoo.uid}])
    )
    state = _one(odoo.execute("pos.session", "read", [[session], ["state"]])).get("state")
    if state == "opening_control":
        odoo.execute("pos.session", "set_opening_control", [[session], 0, ""])
    return session


def _order(session: int, product: int, day: date, sold: int) -> dict[str, Any]:
    return {
        "session_id": session,
        "date_order": f"{day.isoformat()} 12:00:00",
        "pos_reference": REFERENCE,
        "amount_tax": 0,
        "amount_total": sold,
        "amount_paid": sold,
        "amount_return": 0,
        "state": "paid",
        "lines": [
            (
                0,
                0,
                {
                    "product_id": product,
                    "qty": sold,
                    "price_unit": 1,
                    "price_subtotal": sold,
                    "price_subtotal_incl": sold,
                },
            )
        ],
    }


def _move(product: int, uom: int, source: int, dest: int, day: date, delivered: int) -> dict[str, Any]:
    return {
        "product_id": product,
        "product_uom_qty": delivered,
        "uom_id": uom,
        "location_id": source,
        "location_dest_id": dest,
        "origin": REFERENCE,
        "date": f"{day.isoformat()} 06:00:00",
        "state": "done",
        "move_line_ids": [
            (
                0,
                0,
                {
                    "product_id": product,
                    "quantity": delivered,
                    "location_id": source,
                    "location_dest_id": dest,
                    "uom_id": uom,
                    "picked": True,
                },
            )
        ],
    }


def main() -> None:
    rows = days()
    odoo = Odoo(
        os.environ.get("ODOO_URL", "http://127.0.0.1:8069/jsonrpc"),
        os.environ.get("ODOO_DATABASE", "akwara"),
        os.environ.get("ODOO_LOGIN", "admin"),
        os.environ.get("ODOO_PASSWORD", "admin"),
    )
    _wipe(odoo)
    _load(odoo, rows)
    print(f"{BRANCH} {rows[0][0].isoformat()} {rows[-1][0].isoformat()} {len(rows)}")


if __name__ == "__main__":
    main()
