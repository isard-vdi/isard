"""URL validation to prevent SSRF attacks."""

import ipaddress
import socket
from urllib.parse import urljoin, urlparse


def validate_url_not_internal(url):
    """Reject URLs that resolve to private, loopback, link-local or reserved IPs."""
    if not url:
        return
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return
    try:
        results = socket.getaddrinfo(
            hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
        for _, _, _, _, sockaddr in results:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError(
                    f"URL {url} resolves to internal address {sockaddr[0]}"
                )
    except socket.gaierror:
        pass  # DNS resolution failed — allow (will fail on actual request)


def validate_url_scheme(url, allowed_schemes=("http", "https")):
    """Reject URLs with non-allowed schemes (e.g. javascript:, data:)."""
    if not url:
        return
    parsed = urlparse(url.strip())
    if parsed.scheme and parsed.scheme.lower() not in allowed_schemes:
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}")


def safe_requests_get_with_redirect_validation(
    requests_module, url, max_redirects=5, **kwargs
):
    """Like ``requests.get(allow_redirects=True)`` but re-validate the
    target against ``validate_url_not_internal`` at every hop, so a
    public URL cannot redirect into a private/loopback address.

    ``requests_module`` is injected so the helper stays decoupled from
    ``requests`` (tests can stub it). Other kwargs pass through to
    ``get``. Raises ``ValueError`` if any hop is internal, ``RuntimeError``
    if the chain exceeds ``max_redirects``.
    """
    current_url = url
    for _ in range(max_redirects + 1):
        validate_url_not_internal(current_url)
        # Interpose validation per hop: never let requests auto-follow.
        resp = requests_module.get(current_url, **{**kwargs, "allow_redirects": False})
        if resp.status_code not in (301, 302, 303, 307, 308):
            return resp
        next_url = resp.headers.get("Location") or ""
        if not next_url:
            return resp
        next_url = urljoin(current_url, next_url)  # may be relative
        try:
            resp.close()
        except Exception:
            pass
        current_url = next_url
    raise RuntimeError(f"Too many redirects ({max_redirects}) following {url}")
