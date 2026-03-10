import ipaddress
import socket
from urllib.parse import urlparse


class SSRFError(Exception):
    pass


def validate_url_not_internal(url):
    """Resolve hostname and block requests to private/internal IP addresses.

    Raises SSRFError if the URL resolves to a private, loopback, link-local,
    or reserved IP address (including cloud metadata at 169.254.0.0/16).
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL has no hostname")

    try:
        results = socket.getaddrinfo(
            hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
    except socket.gaierror as e:
        raise SSRFError(f"DNS resolution failed for {hostname}: {e}")

    for family, socktype, proto, canonname, sockaddr in results:
        ip_str = sockaddr[0]
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise SSRFError(f"URL resolves to blocked internal address: {ip_str}")
