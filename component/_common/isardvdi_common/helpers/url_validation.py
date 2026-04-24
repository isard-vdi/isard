"""URL validation to prevent SSRF attacks."""

import ipaddress
import socket
from urllib.parse import urlparse


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
