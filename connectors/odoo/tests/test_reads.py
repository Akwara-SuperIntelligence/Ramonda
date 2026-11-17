import ast
import asyncio
from pathlib import Path
from typing import Any

import pytest
from mcp_types import CallToolResult

from odoo import server
from odoo.client import Odoo, OdooError
from odoo.server import mcp

_SECRET = "s3cret"
_OTHER = "other-secret"


class FakeTransport:
    def __init__(self, responses: list[Any], *, error: bool = False) -> None:
        self.responses = responses
        self.payloads: list[dict[str, Any]] = []
        self.error = error

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        if self.error:
            return {"jsonrpc": "2.0", "id": 1, "error": {"message": self.responses[0]}}
        if not self.responses:
            raise AssertionError("unexpected Odoo call")
        return {"jsonrpc": "2.0", "id": 1, "result": self.responses.pop(0)}


def _bind(responses: list[Any], *, error: bool = False) -> FakeTransport:
    fake = FakeTransport(responses, error=error)
    server._client = Odoo(fake, "akwara")
    return fake


def _args(credential: str, login: str = "amina") -> dict[str, str]:
    return {
        "branch": "Westlands",
        "start": "2026-09-01",
        "end": "2026-09-14",
        "login": login,
        "credential": credential,
    }


def _rows(result: CallToolResult | Any) -> Any:
    assert isinstance(result, CallToolResult)
    return result.structured_content


def test_reads_return_row_shapes(capsys: pytest.CaptureFixture[str]) -> None:
    orders = [
        {"id": 1, "date_order": "2026-09-01 09:00:00"},
        {"id": 2, "date_order": "2026-09-08 09:00:00"},
    ]
    lines = [
        {"order_id": [1, "POS/1"], "product_id": [5, "Butter croissant"], "qty": 74},
        {"order_id": [2, "POS/2"], "product_id": [5, "Butter croissant"], "qty": 58},
    ]
    moves = [
        {"date": "2026-09-01 06:00:00", "product_id": [5, "Butter croissant"], "quantity": 80},
    ]
    fake = _bind([7, orders, 7, lines, 7, moves, 8, []])

    sales = asyncio.run(mcp.call_tool("pos_sales", _args(_SECRET)))
    deliveries = asyncio.run(mcp.call_tool("bakery_deliveries", _args(_SECRET)))
    empty = asyncio.run(mcp.call_tool("pos_sales", _args(_OTHER, login="brian")))

    assert _rows(sales) == {
        "result": [
            {"date": "2026-09-01", "product": "Butter croissant", "qty": 74.0},
            {"date": "2026-09-08", "product": "Butter croissant", "qty": 58.0},
        ]
    }
    assert _rows(deliveries) == {
        "result": [
            {"date": "2026-09-01", "product": "Butter croissant", "qty_delivered": 80.0},
        ]
    }
    assert _rows(empty) == {"result": []}

    auths = [args for service, method, args in _calls(fake) if method == "authenticate"]
    reads = [args for service, method, args in _calls(fake) if method == "execute_kw"]
    assert [args[1] for args in auths] == ["amina", "amina", "amina", "brian"]
    assert [args[2] for args in auths] == [_SECRET, _SECRET, _SECRET, _OTHER]
    assert {service for service, method, args in _calls(fake)} <= {"common", "object"}
    assert [args[4] for args in reads] == ["search_read"] * 4
    assert [args[0] for args in reads] == ["akwara"] * 4
    assert [args[3] for args in reads] == [
        "pos.order",
        "pos.order.line",
        "stock.move",
        "pos.order",
    ]
    assert reads[0][5][0] == [
        ["config_id.name", "=", "Westlands"],
        ["date_order", ">=", "2026-09-01 00:00:00"],
        ["date_order", "<=", "2026-09-14 23:59:59"],
        ["state", "in", ["paid", "done"]],
    ]
    assert reads[1][5][0] == [["order_id", "in", [1, 2]]]
    assert reads[1][6] == {"fields": ["order_id", "product_id", "qty"]}
    assert reads[2][5][0] == [
        ["location_dest_id.warehouse_id.name", "=", "Westlands"],
        ["date", ">=", "2026-09-01 00:00:00"],
        ["date", "<=", "2026-09-14 23:59:59"],
        ["state", "=", "done"],
    ]
    assert reads[2][6] == {"fields": ["date", "product_id", "quantity"]}
    assert reads[3][5][0][0] == ["config_id.name", "=", "Westlands"]
    client = server._client
    assert client is not None
    assert set(client.__dict__) == {"_transport", "_database"}

    out = capsys.readouterr().out
    leaked = _SECRET in out or _OTHER in out
    assert not leaked, "stdout leaked the credential"
    lines = [_fields(line) for line in out.splitlines() if line.startswith("odoo-call")]
    assert all(
        line["method"] == "authenticate" or line["operation"] == "search_read" for line in lines
    )
    logins = [line["login"] for line in lines if line["method"] == "authenticate"]
    assert logins == ["amina", "amina", "amina", "brian"]
    assert len(lines) == 8


def test_failed_call_does_not_echo_the_credential() -> None:
    _bind([_SECRET], error=True)
    client = server._client
    assert client is not None
    with pytest.raises(OdooError) as caught:
        client.search_read("amina", _SECRET, "stock.move", [], ["quantity"])
    assert _SECRET not in str(caught.value)

    _bind([False])
    client = server._client
    assert client is not None
    with pytest.raises(OdooError) as caught:
        client.search_read("amina", _SECRET, "stock.move", [], ["quantity"])
    assert _SECRET not in str(caught.value)


def test_module_has_no_odoo_write_call() -> None:
    root = Path(server.__file__).resolve().parent
    writes = {"create", "write", "unlink", "copy"}
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in writes:
                raise AssertionError(f"{path.name} has Odoo write call {node.value}")
            if isinstance(node, ast.Attribute) and node.attr in writes:
                raise AssertionError(f"{path.name} has Odoo write call {node.attr}")
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == {"pos_sales", "bakery_deliveries"}


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split()[1:])


def _calls(fake: FakeTransport) -> list[tuple[str, str, list[Any]]]:
    calls: list[tuple[str, str, list[Any]]] = []
    for payload in fake.payloads:
        params = payload["params"]
        calls.append((params["service"], params["method"], params["args"]))
    return calls
