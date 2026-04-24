"""Hand-written helpers for the generated apiv4 client.

``build_client(service)`` assembles an ``AuthenticatedClient`` with a
fresh service JWT and the correct base URL. Long-running loops should
wrap it in ``with build_client(...) as c:`` for httpx connection
pooling; the minted token has a 20s TTL, so re-enter the context every
iteration or implement a per-request httpx.Auth if TTL matters.

``raise_for_status(response)`` / ``ApiV4Error`` are re-exported for
convenience.
"""

from typing import Literal, Optional

from isardvdi_apiv4_client import AuthenticatedClient

from ._errors import ApiV4Error, raise_for_status
from ._jwt import Role, mint_service_token
from ._url import resolve_base_url

__all__ = ["ApiV4Error", "build_client", "raise_for_status"]


def build_client(
    service: str,
    *,
    role: Role = "admin",
    user_jwt: Optional[str] = None,
) -> AuthenticatedClient:
    """Return an ``AuthenticatedClient`` ready to call apiv4.

    Parameters
    ----------
    service:
        The calling service's container name (e.g. ``"isard-scheduler"``).
    role:
        ``"admin"`` (default) or ``"hypervisor"``. Picks the secret and
        ``kid`` used to mint the JWT. Ignored if ``user_jwt`` is set.
    user_jwt:
        Pre-existing JWT to forward (typically the webapp passing a
        user's Authorization header). When provided, no service JWT is
        minted.
    """
    base_url, verify_ssl = resolve_base_url()
    token = user_jwt if user_jwt is not None else mint_service_token(service, role=role)
    return AuthenticatedClient(
        base_url=base_url,
        token=token,
        verify_ssl=verify_ssl,
        raise_on_unexpected_status=False,
    )
