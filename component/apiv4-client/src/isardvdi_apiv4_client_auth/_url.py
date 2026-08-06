"""Base URL resolution for apiv4.

Replicates the ``container_base_path`` + URL construction semantics of
the legacy REST wrapper for the ``isard-api`` / ``isard-apiv4`` targets
so migrating services see no behavioural drift.
"""

import ipaddress
import os
from typing import Tuple

_BASE_PATH = ""
_DEFAULT_HOST = "isard-apiv4"
_DEFAULT_PORT = 5000


def _is_private_or_loopback_ip(addr: str) -> bool:
    try:
        parsed = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return parsed.is_private or parsed.is_loopback


def resolve_base_url() -> Tuple[str, bool]:
    """Return ``(base_url, verify_ssl)`` for the apiv4 client.

    - No ``API_DOMAIN`` (or the legacy ``isard-api`` sentinel) → in-cluster
      HTTP to ``isard-apiv4:5000``, no TLS verification (self-signed cert
      inside the pod network).
    - ``localhost`` or anything starting with ``isard-`` → in-cluster
      HTTP, no TLS verification.
    - Anything else → HTTPS to that host, TLS verification **off** only
      for private/loopback IP literals (no SAN match possible) and **on**
      for DNS names and public IPs.
    """
    api_domain = os.environ.get("API_DOMAIN", "").strip()
    if not api_domain or api_domain == "isard-api":
        return (f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}{_BASE_PATH}", False)
    if api_domain == "localhost" or api_domain.startswith("isard-"):
        return (f"http://{api_domain}:{_DEFAULT_PORT}{_BASE_PATH}", False)
    verify = not _is_private_or_loopback_ip(api_domain)
    return (f"https://{api_domain}{_BASE_PATH}", verify)
