"""Hand-written helpers for the generated isard-notifier client.

``build_client(service)`` assembles an ``AuthenticatedClient`` with a
fresh service JWT and the correct base URL. The minted token has a 20s
TTL, so re-enter the context every iteration or implement a per-request
``httpx.Auth`` if TTL matters.

JWT minting and error handling are reused from
``isardvdi_apiv4_client_auth`` — the isard-notifier service validates
the same ``kid=isardvdi`` admin-role HS256 tokens that apiv4 and
authentication do (``API_ISARDVDI_SECRET``).

TODO: Consolidate JWT/error helpers into a shared
``isardvdi_service_client_auth`` package now that a third service
client has joined the generation pipeline.
"""

from typing import TYPE_CHECKING, Optional

from isardvdi_apiv4_client_auth._errors import ApiV4Error as _ApiError
from isardvdi_apiv4_client_auth._errors import raise_for_status as _raise_for_status
from isardvdi_apiv4_client_auth._jwt import Role, mint_service_token

from ._url import resolve_base_url

if TYPE_CHECKING:
    from isardvdi_notifier_client import AuthenticatedClient

# Re-export shared error helpers under the local namespace so call
# sites don't need to import from the apiv4 package.
NotifierApiError = _ApiError
raise_for_status = _raise_for_status

__all__ = ["NotifierApiError", "build_client", "raise_for_status"]


def build_client(
    service: str,
    *,
    role: Role = "admin",
    user_jwt: Optional[str] = None,
) -> "AuthenticatedClient":
    """Return an ``AuthenticatedClient`` ready to call isard-notifier.

    Parameters
    ----------
    service:
        The calling service's container name (e.g. ``"isard-apiv4"``).
    role:
        ``"admin"`` (default) or ``"hypervisor"``. Picks the secret and
        ``kid`` used to mint the JWT. Ignored if ``user_jwt`` is set.
    user_jwt:
        Pre-existing JWT to forward. When provided, no service JWT is
        minted.
    """
    from isardvdi_notifier_client import AuthenticatedClient

    base_url, verify_ssl = resolve_base_url()
    token = user_jwt if user_jwt is not None else mint_service_token(service, role=role)
    return AuthenticatedClient(
        base_url=base_url,
        token=token,
        verify_ssl=verify_ssl,
        raise_on_unexpected_status=False,
    )
