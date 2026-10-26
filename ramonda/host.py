"""Verify the caller's token at the door and pass the caller to the components.

The identity provider is named by OIDC_JWKS_URL, OIDC_ISSUER, and OIDC_AUDIENCE.
Claims: email is the user, org is the organisation, groups is the group list, and
clearance is one of CLEARANCE. OIDC_ORG and OIDC_CLEARANCE fill a missing claim.

The host is the only place that verifies a token. Retrieval receives the caller.
"""

import os
from dataclasses import dataclass

__all__ = ["Caller", "caller_from_claims", "caller_from_token", "matching_ids"]

# The order is the clearance order. Keep it equal to the retrieval.clearance enum.
CLEARANCE = ("public", "internal", "confidential", "restricted")

_clients = {}


@dataclass(frozen=True)
class Caller:
    user: str
    org: str
    groups: tuple[str, ...]
    clearance: str


def caller_from_claims(claims):
    # shortcut: email is the id on both sides; Fortune 500 uses an immutable directory id.
    user = str(claims.get("email") or "").strip()
    if claims.get("email_verified") is False:
        raise ValueError("token email is not verified")
    org = str(claims.get("org") or "").strip()
    if not user or not org:
        raise ValueError("token has no email or org claim")
    clearance = str(claims.get("clearance") or "public")
    if clearance not in CLEARANCE:
        raise ValueError(f"token clearance {clearance!r}")
    groups = claims.get("groups") or ()
    if isinstance(groups, str):
        groups = (groups,)
    return Caller(user, org, tuple(str(group) for group in groups), clearance)


def _key(token):
    url = os.environ.get("OIDC_JWKS_URL")
    if not url:
        raise SystemExit("OIDC_JWKS_URL is missing.")
    client = _clients.get(url)
    if client is None:
        from jwt import PyJWKClient

        client = _clients[url] = PyJWKClient(url)
    return client.get_signing_key_from_jwt(token).key


def _decode(token, key, issuer, audience):
    from jwt import decode

    return decode(token, key, algorithms=["RS256"], issuer=issuer, audience=audience)


def caller_from_token(token):
    if not token:
        raise ValueError("token is missing")
    issuer = os.environ.get("OIDC_ISSUER")
    audience = os.environ.get("OIDC_AUDIENCE")
    if not issuer or not audience:
        raise SystemExit("OIDC_ISSUER and OIDC_AUDIENCE are missing.")
    claims = _decode(token, _key(token), issuer, audience)
    # shortcut: one organisation and one operator; Fortune 500 puts both claims in the token.
    claims.setdefault("org", os.environ.get("OIDC_ORG"))
    claims.setdefault("clearance", os.environ.get("OIDC_CLEARANCE"))
    return caller_from_claims(claims)


def matching_ids(token, filters=None):
    from . import retrieval

    return retrieval.matching_ids(caller_from_token(token), filters)


def _self_check():
    caller = caller_from_claims(
        {
            "email": "hassan@akwara",
            "org": "akwara",
            "groups": ["finance"],
            "clearance": "confidential",
        }
    )
    assert caller.user == "hassan@akwara"
    assert caller.org == "akwara"
    assert caller.groups == ("finance",)
    assert caller.clearance == "confidential"
    default = caller_from_claims({"email": "a", "org": "b"})
    assert default.groups == () and default.clearance == "public"
    assert caller_from_claims({"email": "a", "org": "b", "groups": "finance"}).groups == (
        "finance",
    )
    for bad in (
        {},
        {"email": "a"},
        {"org": "b"},
        {"sub": "a", "org": "b"},
        {"email": "a", "org": "b", "clearance": "secret"},
        {"email": "a", "org": "b", "email_verified": False},
    ):
        try:
            caller_from_claims(bad)
        except ValueError:
            continue
        raise AssertionError(f"claims were accepted: {bad}")
    try:
        caller_from_token("")
    except ValueError:
        pass
    else:
        raise AssertionError("an empty token was accepted")

    try:
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        print("skip signed-token check: pyjwt[crypto] is not installed", flush=True)
        return
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {
        "email": "maria@othercorp.com",
        "org": "othercorp",
        "aud": "ramonda",
        "iss": "https://id.example",
        "exp": 4102444800,
    }
    token = jwt.encode(claims, key, algorithm="RS256")
    public = key.public_key()
    assert _decode(token, public, "https://id.example", "ramonda")["org"] == "othercorp"
    try:
        _decode(token, public, "https://id.example", "another-app")
    except jwt.InvalidAudienceError:
        pass
    else:
        raise AssertionError("a wrong audience was accepted")
    try:
        _decode(jwt.encode({**claims, "exp": 1}, key, algorithm="RS256"), public, "https://id.example", "ramonda")
    except jwt.ExpiredSignatureError:
        pass
    else:
        raise AssertionError("an expired token was accepted")
    forged_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(claims, forged_key, algorithm="RS256")
    try:
        _decode(forged, public, "https://id.example", "ramonda")
    except jwt.InvalidSignatureError:
        pass
    else:
        raise AssertionError("a forged signature was accepted")


if __name__ == "__main__":
    _self_check()
