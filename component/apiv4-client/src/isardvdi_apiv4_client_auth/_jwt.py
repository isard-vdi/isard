"""Service JWT minting for apiv4.

Matches the contract the apiv4 auth middleware expects: ``kid`` +
``session_id: "isardvdi-service"`` + ``data.role_id`` + secret.

The shape replicates the ``header_auth`` semantics of the legacy REST
wrappers (admin role for most services; hypervisor role for the
hypervisor container, which uses a distinct secret and ``kid``). apiv4
verifies these tokens in
``component/apiv4/src/api/dependencies/jwt_token.py``.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt

Role = Literal["admin", "hypervisor"]

_ADMIN_SECRET_ENV = "API_ISARDVDI_SECRET"
_HYPERVISOR_SECRET_ENV = "API_HYPERVISORS_SECRET"

_DEFAULT_TTL_SECONDS = 20


def mint_service_token(
    service: str,
    *,
    role: Role = "admin",
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> str:
    """Mint a short-lived HS256 JWT for service-to-service apiv4 calls.

    Parameters
    ----------
    service:
        The calling service's container name (e.g. ``"isard-scheduler"``).
        Stored as ``data.user_id`` so apiv4 audit logs can trace origin.
    role:
        ``"admin"`` for the bulk of services; ``"hypervisor"`` for the
        hypervisor container only. The two use different secrets and
        different ``kid`` values.
    ttl_seconds:
        JWT expiry offset. Default matches the 20s used by the legacy
        REST wrapper. Do not raise this without reviewing the refresh
        strategy in long-running loops.
    """
    now = datetime.now(tz=timezone.utc)
    exp = now + timedelta(seconds=ttl_seconds)
    if role == "admin":
        kid = "isardvdi"
        secret = os.environ[_ADMIN_SECRET_ENV]
        category_id = "*"
    elif role == "hypervisor":
        kid = "isardvdi-hypervisors"
        secret = os.environ[_HYPERVISOR_SECRET_ENV]
        category_id = "default"
    else:
        raise ValueError(f"unsupported role: {role!r}")

    payload = {
        "exp": exp,
        "kid": kid,
        "session_id": "isardvdi-service",
        "data": {
            "role_id": role,
            "user_id": service,
            "category_id": category_id,
        },
    }
    return jwt.encode(payload, secret, algorithm="HS256")
