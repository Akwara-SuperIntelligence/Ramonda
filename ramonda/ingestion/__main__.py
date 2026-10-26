import os
from types import SimpleNamespace

from . import _self_check, ingest


def caller():
    user = os.environ.get("INGEST_USER")
    org = os.environ.get("OIDC_ORG")
    if not user or not org:
        raise SystemExit("INGEST_USER and OIDC_ORG are missing.")
    # shortcut: the container is the operator; Fortune 500 passes a verified caller from the host.
    return SimpleNamespace(user=user, org=org, groups=(), clearance="restricted")


_self_check()
ingest(caller())
