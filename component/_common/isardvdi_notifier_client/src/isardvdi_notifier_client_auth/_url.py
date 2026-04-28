"""Base URL resolution for the isard-notifier service.

Replicates the ``container_base_path`` + URL construction semantics of
the legacy REST wrapper for the ``isard-notifier`` target so migrating
callers see no behavioural drift.

Unlike ``isard-authentication``, the notifier's generated OpenAPI spec
paths already include the ``/notifier`` prefix (the Flask routes are
declared as ``@app.route("/notifier/mail/...")`` and there is no
StripPrefix on the way in). Therefore the base URL must NOT include
``/notifier`` — the paths already do.
"""

import ipaddress
import os
from typing import Tuple

_DEFAULT_HOST = "isard-notifier"
_DEFAULT_PORT = 5000


def _is_private_or_loopback_ip(addr: str) -> bool:
    try:
        parsed = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return parsed.is_private or parsed.is_loopback


def resolve_base_url() -> Tuple[str, bool]:
    """Return ``(base_url, verify_ssl)`` for the notifier client.

    - No ``NOTIFIER_URL`` → in-cluster HTTP to
      ``isard-notifier:5000``, no TLS verification.
    - ``localhost`` or anything starting with ``isard-`` → in-cluster
      HTTP, no TLS verification.
    - Anything else → HTTPS to that host, TLS verification **off** only
      for private/loopback IP literals (no SAN match possible) and **on**
      for DNS names and public IPs.
    """
    notifier_url = os.environ.get("NOTIFIER_URL", "").strip()
    if not notifier_url:
        return (f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}", False)
    if notifier_url.startswith("http://") or notifier_url.startswith("https://"):
        base = notifier_url.rstrip("/")
        verify = not notifier_url.startswith("http://")
        return (base, verify)
    if notifier_url == "localhost" or notifier_url.startswith("isard-"):
        return (f"http://{notifier_url}:{_DEFAULT_PORT}", False)
    verify = not _is_private_or_loopback_ip(notifier_url)
    return (f"https://{notifier_url}", verify)
