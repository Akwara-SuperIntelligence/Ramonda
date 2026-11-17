import json
from typing import Any, Protocol, cast
from urllib import request


class OdooError(Exception):
    pass


class Transport(Protocol):
    def call(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class JsonRpcTransport:
    def __init__(self, url: str) -> None:
        self.url = url

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode()
        req = request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=30) as response:
            parsed: Any = json.loads(response.read())
        if not isinstance(parsed, dict):
            raise OdooError("Odoo call failed")
        return cast(dict[str, Any], parsed)


class Odoo:
    def __init__(self, transport: Transport, database: str) -> None:
        self._transport = transport
        self._database = database

    def search_read(
        self,
        login: str,
        credential: str,
        model: str,
        domain: list[list[Any]],
        fields: list[str],
    ) -> list[dict[str, Any]]:
        uid = self._uid(login, credential)
        rows = self._rpc(
            "object",
            "execute_kw",
            [
                self._database,
                uid,
                credential,
                model,
                "search_read",
                [domain],
                {"fields": fields},
            ],
        )
        return _records(rows)

    def _uid(self, login: str, credential: str) -> int:
        uid = self._rpc(
            "common",
            "authenticate",
            [self._database, login, credential, {}],
        )
        if type(uid) is not int:
            raise OdooError("Odoo authentication failed")
        return uid

    def _rpc(self, service: str, method: str, args: list[Any]) -> Any:
        login = _text(args, 1) if method == "authenticate" else ""
        if any(char.isspace() for char in login):
            login = ""
        model = _text(args, 3) if method == "execute_kw" else ""
        operation = _text(args, 4) if method == "execute_kw" else ""
        print(
            f"odoo-call service={service} method={method} model={model} "
            f"operation={operation} login={login}",
            flush=True,
        )
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": 1,
        }
        body = self._transport.call(payload)
        if body.get("error") is not None or "result" not in body:
            raise OdooError("Odoo call failed")
        return body["result"]


def _text(args: list[Any], index: int) -> str:
    value = args[index] if len(args) > index else None
    return value if isinstance(value, str) else ""


def _records(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise OdooError("Odoo call failed")
    rows: list[dict[str, Any]] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise OdooError("Odoo call failed")
        rows.append(cast(dict[str, Any], item))
    return rows
