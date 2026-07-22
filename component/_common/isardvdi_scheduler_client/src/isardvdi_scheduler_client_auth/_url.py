"""Base URL resolution for the isard-scheduler service.

Replicates the ``container_base_path`` + URL construction semantics of
the legacy REST wrapper for the ``isard-scheduler`` target so migrating
callers see no behavioural drift.

Unlike the legacy wrapper (which appended ``/scheduler`` to the base
URL), the generated OpenAPI spec paths already include the
``/scheduler`` prefix (the Flask routes are declared as
``@app.route("/scheduler/...")`` and there is no StripPrefix on the way
in). Therefore the base URL must NOT include ``/scheduler`` — the paths
already do.
"""

import ipaddress
import os
from typing import Tuple

_DEFAULT_HOST = "isard-scheduler"
_DEFAULT_PORT = 5000


def _is_private_or_loopback_ip(addr: str) -> bool:
    try:
        parsed = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return parsed.is_private or parsed.is_loopback


def resolve_base_url() -> Tuple[str, bool]:
    """Return ``(base_url, verify_ssl)`` for the scheduler client.

    - No ``SCHEDULER_URL`` → in-cluster HTTP to
      ``isard-scheduler:5000``, no TLS verification.
    - ``localhost`` or anything starting with ``isard-`` → in-cluster
      HTTP, no TLS verification.
    - Anything else → HTTPS to that host, TLS verification **off** only
      for private/loopback IP literals (no SAN match possible) and **on**
      for DNS names and public IPs.
    """
    scheduler_url = os.environ.get("SCHEDULER_URL", "").strip()
    if not scheduler_url:
        return (f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}", False)
    if scheduler_url.startswith("http://") or scheduler_url.startswith("https://"):
        base = scheduler_url.rstrip("/")
        verify = not scheduler_url.startswith("http://")
        return (base, verify)
    if scheduler_url == "localhost" or scheduler_url.startswith("isard-"):
        return (f"http://{scheduler_url}:{_DEFAULT_PORT}", False)
    verify = not _is_private_or_loopback_ip(scheduler_url)
    return (f"https://{scheduler_url}", verify)
