"""Base URL resolution for the isard-authentication service.

Replicates the ``container_base_path`` + URL construction semantics of
the legacy REST wrapper for the ``isard-authentication`` target so
migrating services see no behavioural drift.

Note: the generated OpenAPI spec paths are post-``StripPrefix`` (so
e.g. ``/migrate-user`` instead of ``/authentication/migrate-user``).
Therefore the base URL must include the ``/authentication`` prefix
that the Go mux strips before dispatch.
"""

import ipaddress
import os
from typing import Tuple

_BASE_PATH = "/authentication"
_DEFAULT_HOST = "isard-authentication"
_DEFAULT_PORT = 1313


def _is_private_or_loopback_ip(addr: str) -> bool:
    try:
        parsed = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return parsed.is_private or parsed.is_loopback


def resolve_base_url() -> Tuple[str, bool]:
    """Return ``(base_url, verify_ssl)`` for the authentication client.

    - No ``AUTH_URL`` → in-cluster HTTP to
      ``isard-authentication:1313/authentication``, no TLS verification.
    - ``localhost`` or anything starting with ``isard-`` → in-cluster
      HTTP, no TLS verification.
    - Anything else → HTTPS to that host, TLS verification **off** only
      for private/loopback IP literals (no SAN match possible) and **on**
      for DNS names and public IPs.
    """
    auth_url = os.environ.get("AUTH_URL", "").strip()
    if not auth_url:
        return (f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}{_BASE_PATH}", False)
    # ``AUTH_URL`` in integration tests is a full URL like
    # ``http://isard-authentication:1313``. Strip trailing slash and
    # append the ``/authentication`` prefix.
    if auth_url.startswith("http://") or auth_url.startswith("https://"):
        base = auth_url.rstrip("/") + _BASE_PATH
        verify = not auth_url.startswith("http://")
        return (base, verify)
    # Plain host — mirror apiv4 semantics.
    if auth_url == "localhost" or auth_url.startswith("isard-"):
        return (f"http://{auth_url}:{_DEFAULT_PORT}{_BASE_PATH}", False)
    verify = not _is_private_or_loopback_ip(auth_url)
    return (f"https://{auth_url}{_BASE_PATH}", verify)
