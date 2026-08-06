"""Hand-written helpers for the generated apiv4 client.

``build_client(service)`` assembles an ``AuthenticatedClient`` with a
fresh service JWT and the correct base URL. A fresh client is cheap:
every one of them borrows the process-wide connection pool from
``_transport``, so the minted token can keep its 20s TTL without paying
for a handshake per call.

``raise_for_status(response)`` / ``ApiV4Error`` are re-exported for
convenience.
"""

from typing import TYPE_CHECKING, Literal, Optional

from ._errors import ApiV4Error, raise_for_status
from ._jwt import Role, mint_service_token
from ._transport import POOL_TIMEOUT, shared_transport
from ._url import resolve_base_url

if TYPE_CHECKING:
    from isardvdi_apiv4_client import AuthenticatedClient

__all__ = ["ApiV4Error", "build_client", "raise_for_status"]


def build_client(
    service: str,
    *,
    role: Role = "admin",
    user_jwt: Optional[str] = None,
) -> "AuthenticatedClient":
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
    from isardvdi_apiv4_client import AuthenticatedClient

    base_url, verify_ssl = resolve_base_url()
    token = user_jwt if user_jwt is not None else mint_service_token(service, role=role)
    return AuthenticatedClient(
        base_url=base_url,
        token=token,
        verify_ssl=verify_ssl,
        raise_on_unexpected_status=False,
        timeout=POOL_TIMEOUT,
        httpx_args={"transport": shared_transport(verify=verify_ssl)},
    )
