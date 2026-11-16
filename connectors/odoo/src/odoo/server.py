import os
from datetime import date
from typing import Any, TypedDict, cast

from mcp.server import MCPServer

from .client import JsonRpcTransport, Odoo, OdooError


class SaleRow(TypedDict):
    date: str
    product: str
    qty: float


class DeliveryRow(TypedDict):
    date: str
    product: str
    qty_delivered: float


mcp = MCPServer("odoo")
_client: Odoo | None = None


def odoo_client() -> Odoo:
    """Process client. `ODOO_URL` is the `/jsonrpc` endpoint and `ODOO_DATABASE` is the database."""
    global _client
    if _client is None:
        _client = Odoo(JsonRpcTransport(os.environ["ODOO_URL"]), os.environ["ODOO_DATABASE"])
    return _client


def _span(field: str, start: date, end: date) -> list[list[Any]]:
    opening = f"{start.isoformat()} 00:00:00"
    closing = f"{end.isoformat()} 23:59:59"
    return [[field, ">=", opening], [field, "<=", closing]]


def _id(value: object) -> int:
    if type(value) is int:
        return value
    items = _objects(value)
    if items and type(items[0]) is int:
        return items[0]
    raise OdooError("Odoo record shape")


def _day(value: object) -> str:
    if isinstance(value, str) and len(value) >= 10:
        return value[:10]
    raise OdooError("Odoo record shape")


def _name(value: object) -> str:
    if isinstance(value, str):
        return value
    items = _objects(value)
    if items and len(items) >= 2 and isinstance(items[1], str):
        return items[1]
    raise OdooError("Odoo record shape")


def _objects(value: object) -> list[object] | None:
    if isinstance(value, list):
        return cast(list[object], value)
    return None


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise OdooError("Odoo record shape")
    return float(value)


@mcp.tool()
def pos_sales(branch: str, start: date, end: date, login: str, credential: str) -> list[SaleRow]:
    """Read point-of-sale lines for one branch and date range."""
    client = odoo_client()
    orders = client.search_read(
        login,
        credential,
        "pos.order",
        [
            ["config_id.name", "=", branch],
            *_span("date_order", start, end),
            ["state", "in", ["paid", "done"]],
        ],
        ["id", "date_order"],
    )
    if not orders:
        return []
    dates = {_id(order["id"]): _day(order["date_order"]) for order in orders}
    lines = client.search_read(
        login,
        credential,
        "pos.order.line",
        [["order_id", "in", list(dates)]],
        ["order_id", "product_id", "qty"],
    )
    return [
        SaleRow(
            date=dates[_id(line["order_id"])],
            product=_name(line["product_id"]),
            qty=_number(line["qty"]),
        )
        for line in lines
    ]


@mcp.tool()
def bakery_deliveries(
    branch: str, start: date, end: date, login: str, credential: str
) -> list[DeliveryRow]:
    """Read bakery delivery lines for one branch and date range."""
    moves = odoo_client().search_read(
        login,
        credential,
        "stock.move",
        [
            ["location_dest_id.warehouse_id.name", "=", branch],
            *_span("date", start, end),
            ["state", "=", "done"],
        ],
        ["date", "product_id", "quantity"],
    )
    return [
        DeliveryRow(
            date=_day(move["date"]),
            product=_name(move["product_id"]),
            qty_delivered=_number(move["quantity"]),
        )
        for move in moves
    ]
