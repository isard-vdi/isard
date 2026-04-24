"""Base URL resolution for apiv4.

Lifted from ``component/_common/isardvdi_common/connections/api_rest.py``
(the ``isard-api`` / ``isard-apiv4`` branches of ``container_base_path``
+ URL construction). Semantics preserved so migrating services see no
behavioural drift.
"""

import os
from typing import Tuple

_BASE_PATH = "/api/v4"
_DEFAULT_HOST = "isard-apiv4"
_DEFAULT_PORT = 5000


def _is_ipv4(addr: str) -> bool:
    parts = addr.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def resolve_base_url() -> Tuple[str, bool]:
    """Return ``(base_url, verify_ssl)`` for the apiv4 client.

    - No ``API_DOMAIN`` (or the legacy ``isard-api`` sentinel) → in-cluster
      HTTP to ``isard-apiv4:5000``, no TLS verification (self-signed cert
      inside the pod network).
    - ``localhost`` or anything starting with ``isard-`` → in-cluster
      HTTP, no TLS verification.
    - Anything else → HTTPS to that host, TLS verification **off** for
      raw IPv4 addresses (no SAN match possible) and **on** for DNS names.
    """
    api_domain = os.environ.get("API_DOMAIN", "").strip()
    if not api_domain or api_domain == "isard-api":
        return (f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}{_BASE_PATH}", False)
    if api_domain == "localhost" or api_domain.startswith("isard-"):
        return (f"http://{api_domain}:{_DEFAULT_PORT}{_BASE_PATH}", False)
    verify = not _is_ipv4(api_domain)
    return (f"https://{api_domain}{_BASE_PATH}", verify)
