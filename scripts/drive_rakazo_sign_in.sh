#!/bin/sh
# Drive Amina and Brian through Rakazo v0.9.0, Keycloak, and the gateway.
# Curl uses --resolve for keycloak and deploy/keycloak/dev-only-ca.crt.
# A browser needs `127.0.0.1 keycloak` in the hosts file and trust of that CA.
# A chat turn that calls whoami needs DEEPSEEK_API_KEY. This script stops and
# names that variable when it is unset.
set -eu
cd -- "$(dirname -- "$0")/.."
exec python3 - "$@" <<'PY'
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path

ROOT = Path.cwd()
WEB = os.environ.get("RAKAZO_WEB", "http://127.0.0.1:5173")
KEYCLOAK = os.environ.get("KEYCLOAK_URL", "https://keycloak:8443")
GATEWAY = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8080")
CA = ROOT / "deploy/keycloak/dev-only-ca.crt"
CONFIG = json.loads((ROOT / "clients/akwara-cafe/gateway-mcp.json").read_text())
USERS = (("amina", "amina"), ("brian", "brian"))
WHOAMI = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "whoami", "arguments": {"user_id": "brian", "tenant_id": "other"}},
}


def curl(jar, method, url, body=None, headers=None, form=False, max_time=30):
    cmd = [
        "curl",
        "-sS",
        "-D",
        "-",
        "--max-time",
        str(max_time),
        "--max-redirs",
        "0",
        "--cacert",
        str(CA),
        "--resolve",
        "keycloak:8443:127.0.0.1",
        "-c",
        jar,
        "-b",
        jar,
        "-X",
        method,
        "-w",
        "\n%{http_code}",
    ]
    for key, value in (headers or {}).items():
        cmd.extend(["-H", f"{key}: {value}"])
    if body is not None:
        if form:
            cmd.extend(["-H", "content-type: application/x-www-form-urlencoded", "--data", urllib.parse.urlencode(body)])
        else:
            cmd.extend(["-H", "content-type: application/json", "--data", json.dumps(body)])
    cmd.append(url)
    raw = subprocess.check_output(cmd, text=True)
    head, _, status = raw.rpartition("\n")
    header_text, _, payload = head.partition("\r\n\r\n")
    if not payload and "\n\n" in head:
        header_text, _, payload = head.partition("\n\n")
    headers_out = {}
    for line in header_text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            headers_out[key.strip().lower()] = value.strip()
    return int(status.strip() or "0"), headers_out, payload


def wait(url, seconds=240):
    jar = tempfile.mktemp(prefix="rakazo-wait-")
    deadline = time.time() + seconds
    last = ""
    while time.time() < deadline:
        try:
            remaining = max(1, int(deadline - time.time()))
            status, _, payload = curl(jar, "GET", url, max_time=min(10, remaining))
            if status and status < 500:
                return
            last = payload[:200]
        except subprocess.CalledProcessError as error:
            last = error.stderr or str(error) if isinstance(error.stderr, str) else str(error)
        time.sleep(2)
    raise SystemExit(f"not ready: {url} ({last})")


def form_fields(html):
    import html as html_lib

    match = re.search(r'<form[^>]*action="([^"]+)"', html, re.I)
    if not match:
        return None, {}
    fields = {}
    for tag in re.findall(r"<input\b[^>]*>", html, re.I):
        name = re.search(r'name="([^"]+)"', tag)
        if not name:
            continue
        value = re.search(r'value="([^"]*)"', tag)
        fields[html_lib.unescape(name.group(1))] = html_lib.unescape(value.group(1)) if value else ""
    return html_lib.unescape(match.group(1)), fields


def walk(jar, url, username, password, stop_path):
    for _ in range(15):
        status, headers, payload = curl(jar, "GET", url, headers={"accept": "text/html,application/json"})
        location = headers.get("location")
        if location:
            url = urllib.parse.urljoin(url, location)
            if stop_path in url:
                return url
            continue
        if stop_path in url:
            return url
        action, fields = form_fields(payload)
        if not action:
            raise SystemExit(f"no form at {url} status {status}: {payload[:400]}")
        target = urllib.parse.urljoin(url, action)
        if "username" in fields:
            fields["username"] = username
            fields["password"] = password
        else:
            fields["accept"] = fields.get("accept") or "Yes"
        status, headers, payload = curl(jar, "POST", target, fields, form=True)
        location = headers.get("location")
        if not location:
            raise SystemExit(f"form post stayed at {target} status {status}: {payload[:400]}")
        url = urllib.parse.urljoin(target, location)
        if stop_path in url:
            return url
    raise SystemExit("too many redirects")


def rpc(jar, path, payload):
    status, _, body = curl(
        jar,
        "POST",
        f"{WEB}/rpc/{path}",
        {"json": payload},
        {"origin": WEB, "accept": "application/json"},
    )
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise SystemExit(f"{path} status {status}: {body[:400]!r}")
    if status >= 400 or "json" not in parsed:
        raise SystemExit(f"{path} status {status}: {parsed}")
    return parsed["json"]


def sign_in(username, password):
    jar = tempfile.mktemp(prefix=f"rakazo-{username}-")
    Path(jar).write_text("")
    status, _, body = curl(
        jar,
        "POST",
        f"{WEB}/api/auth/sign-in/social",
        {
            "provider": "oidc",
            "callbackURL": f"{WEB}/",
            "errorCallbackURL": f"{WEB}/sign-in",
            "disableRedirect": True,
        },
        {"origin": WEB, "accept": "application/json"},
    )
    if status != 200:
        raise SystemExit(f"sign-in start {username} status {status}: {body[:500]!r}")
    callback = walk(jar, json.loads(body)["url"], username, password, "/api/auth/callback/oidc")
    if "error=" in callback:
        raise SystemExit(f"oidc callback {username} refused: {callback}")
    status, headers, body = curl(jar, "GET", callback, headers={"origin": WEB, "accept": "text/html"})
    if "error=" in (headers.get("location") or ""):
        raise SystemExit(f"oidc callback {username} refused: {headers.get('location')}")
    if headers.get("location"):
        status, _, body = curl(jar, "GET", urllib.parse.urljoin(callback, headers["location"]), headers={"origin": WEB})
    if status >= 400:
        raise SystemExit(f"oidc callback {username} status {status}: {body[:400]!r}")
    status, _, body = curl(jar, "GET", f"{WEB}/api/auth/get-session", headers={"origin": WEB, "accept": "application/json"})
    session = json.loads(body)
    user = session.get("user") or {}
    print(f"session {username}: email={user.get('email')} name={user.get('name')}")
    email = (user.get("email") or "").lower()
    name = (user.get("name") or "").lower()
    if username not in email and username not in name:
        raise SystemExit(f"{username} session is {user}")
    return jar


def direct_whoami(username, password):
    jar = tempfile.mktemp(prefix="gateway-direct-")
    Path(jar).write_text("")
    status, _, body = curl(
        jar,
        "POST",
        f"{KEYCLOAK}/realms/akwara-cafe/protocol/openid-connect/token",
        {
            "grant_type": "password",
            "client_id": "gateway",
            "client_secret": "gateway",
            "username": username,
            "password": password,
        },
        form=True,
    )
    token = json.loads(body).get("access_token") if body.startswith("{") else None
    if status != 200 or not token:
        raise SystemExit(f"gateway client token {username} status {status}: {body[:300]!r}")
    status, _, body = curl(
        jar,
        "POST",
        f"{GATEWAY}/mcp",
        WHOAMI,
        {
            "authorization": f"Bearer {token}",
            "accept": "application/json, text/event-stream",
        },
    )
    payload = json.loads(body)
    text = payload["result"]["content"][0]["text"]
    print(f"direct whoami {username}: {text}")
    if text != username:
        raise SystemExit(f"direct whoami returned {text}")


def connect(jar, server_id, username, password):
    begun = rpc(jar, "mcp/oauth/begin", {"serverId": server_id})
    print(f"oauth begin {username}: {begun.get('status')}")
    if begun.get("status") == "already_connected":
        return
    if begun.get("status") != "authorization_required":
        raise SystemExit(f"oauth begin {username}: {begun}")
    callback = walk(jar, begun["authorizationUrl"], username, password, "/mcp/oauth/callback")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(callback).query)
    code = (query.get("code") or [""])[0]
    state = (query.get("state") or [""])[0]
    if not code or not state:
        raise SystemExit(f"oauth callback missing code for {username}: {callback}")
    done = rpc(jar, "mcp/oauth/complete", {"sessionId": begun["sessionId"], "code": code, "state": state})
    print(f"oauth complete {username}: {done}")


def bot_reply(snapshot):
    parts = []
    for message in snapshot.get("messages") or []:
        if message.get("role") != "bot":
            continue
        for block in message.get("blocks") or []:
            if block.get("kind") == "text" and block.get("text"):
                parts.append(block["text"].strip())
            if block.get("kind") == "app" and block.get("tool") == "whoami":
                parts.append(json.dumps(block.get("toolResult")))
    return parts[-1] if parts else ""


def chat_whoami(jar, server_id, username):
    rpc(jar, "autoReview/set", {"mode": "never"})
    bots = rpc(jar, "bots/list", {})
    if not isinstance(bots, list):
        raise SystemExit(f"bot list {username}: {bots}")
    bot = next((row for row in bots if row.get("name") == "Akwara"), None)
    if bot is None:
        bot = rpc(
            jar,
            "bots/create",
            {
                "name": "Akwara",
                "spawnKey": "gateway-whoami",
                "instructions": "When asked who is signed in, call the whoami tool and reply with only its result.",
            },
        )
    rpc(jar, "mcp/servers/agents", {"id": server_id, "allBots": True, "botIds": []})
    sent = rpc(
        jar,
        "threads/send",
        {
            "botId": bot["id"],
            "text": "Call the whoami tool now. Reply with only the tool result.",
            "clientNonce": f"whoami-{username}-{int(time.time())}",
        },
    )
    run_id = sent["runId"]
    deadline = time.time() + 180
    terminal = None
    while time.time() < deadline:
        active = (rpc(jar, "runs/list", {"filter": "active"}).get("runs")) or []
        row = next((item for item in active if item.get("runId") == run_id), None)
        if row and row.get("status") in ("failed", "cancelled", "waiting_input"):
            terminal = row
            break
        recent = (rpc(jar, "runs/list", {"filter": "recent"}).get("runs")) or []
        done = next((item for item in recent if item.get("runId") == run_id), None)
        if done:
            terminal = done
            break
        time.sleep(3)
    else:
        raise SystemExit(f"whoami {username} did not finish")
    snapshot = rpc(jar, "threads/get", {"botId": bot["id"]})
    if terminal.get("status") != "completed":
        error = (snapshot.get("run") or {}).get("error")
        raise SystemExit(f"whoami {username} run {terminal.get('status')}: {error}")
    answer = bot_reply(snapshot)
    print(f"whoami through Rakazo {username}: {answer}")
    if answer.strip().lower() != username:
        raise SystemExit(f"whoami through Rakazo for {username} returned {answer!r}")
    return answer


def main():
    wait(f"{KEYCLOAK}/realms/akwara-cafe/.well-known/openid-configuration")
    wait(f"{WEB}/")
    wait(f"{GATEWAY}/.well-known/oauth-protected-resource/mcp")
    direct_whoami("amina", "amina")
    for username, password in USERS:
        jar = sign_in(username, password)
        servers = rpc(jar, "mcp/servers/list", {})
        if not isinstance(servers, list):
            raise SystemExit(f"server list {username}: {servers}")
        if not servers:
            created = rpc(jar, "mcp/servers/create", CONFIG)
            print(f"registered {created['endpoint']} id={created['id']}")
            servers = rpc(jar, "mcp/servers/list", {})
        endpoints = [row.get("endpoint") for row in servers]
        print(f"mcp servers {username}: {endpoints}")
        if endpoints != ["http://gateway:8080/mcp"]:
            raise SystemExit(f"{username} mcp servers are not only the gateway: {servers}")
        connect(jar, servers[0]["id"], username, password)
        tested = rpc(jar, "mcp/servers/test", {"id": servers[0]["id"]})
        health = tested.get("health") or {}
        print(f"mcp test {username}: {json.dumps(health)} oauth={tested.get('oauthStatus')}")
        if health.get("status") != "ok" or health.get("toolCount") != 1:
            raise SystemExit(f"mcp test {username} failed: {json.dumps(health)}")
        if os.environ.get("DEEPSEEK_API_KEY"):
            chat_whoami(jar, servers[0]["id"], username)
    if os.environ.get("DEEPSEEK_API_KEY"):
        return 0
    print("DEEPSEEK_API_KEY is unset.")
    print("Rakazo defaults PI_DEFAULT_PROVIDER to deepseek.")
    print("A chat turn that calls whoami needs DEEPSEEK_API_KEY on rakazo-api and rakazo-worker.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
PY
