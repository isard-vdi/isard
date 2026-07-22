# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``url_validation``: SSRF protections used wherever
apiv4 / webapp resolves a user-provided URL.

Two functions:

- ``validate_url_not_internal(url)`` rejects URLs whose hostname
  resolves to a private / loopback / link-local / reserved IP. This
  is the primary SSRF gate — without it, a user could submit
  ``http://127.0.0.1/...`` or ``http://169.254.169.254/...`` (cloud
  metadata) and have the server fetch it on their behalf.
- ``validate_url_scheme(url, allowed_schemes)`` rejects non-allowed
  URL schemes (``javascript:``, ``data:``, ``file:``, ``gopher:``,
  …) before any further processing.

Contract being pinned: both functions are silent on missing /
malformed input (defensive — the surrounding code may be checking
optional URL fields), and both raise ``ValueError`` on rejection.
"""

import socket
from unittest.mock import patch

import pytest
from isardvdi_common.helpers.url_validation import (
    validate_url_not_internal,
    validate_url_scheme,
)

# ─────────────────────────────────────────────────────────────────────
# validate_url_not_internal
# ─────────────────────────────────────────────────────────────────────


def _fake_getaddrinfo(ip):
    """Return a getaddrinfo-shaped tuple list for ``ip``. The real
    getaddrinfo returns 5-tuples ``(family, socktype, proto,
    canonname, sockaddr)`` where ``sockaddr`` is ``(host, port)``
    for IPv4. The validator only reads ``sockaddr[0]``.
    """
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]


def test_validate_url_not_internal_passes_public_ip():
    """A URL whose host resolves to a routable public IP must pass
    silently. 8.8.8.8 (Google DNS) is the canonical "definitely
    not private" address.
    """
    with patch.object(socket, "getaddrinfo", return_value=_fake_getaddrinfo("8.8.8.8")):
        # Returns None (silent) — does NOT raise.
        assert validate_url_not_internal("https://example.com/path") is None


@pytest.mark.parametrize(
    "internal_ip, label",
    [
        ("127.0.0.1", "loopback ipv4"),
        ("10.0.0.5", "private 10/8"),
        ("172.16.0.1", "private 172.16/12"),
        ("192.168.1.1", "private 192.168/16"),
        ("169.254.169.254", "link-local (cloud metadata)"),
        ("0.0.0.0", "reserved / unspecified"),
        ("::1", "loopback ipv6"),
        ("fe80::1", "link-local ipv6"),
    ],
)
def test_validate_url_not_internal_rejects_internal_addresses(internal_ip, label):
    """Each canonical SSRF target IP must trip the validator. The
    ``label`` shows up in pytest output for failure triage.

    169.254.169.254 is the AWS / GCP cloud metadata endpoint —
    a very high-value SSRF target. If this case fails, every
    server in a cloud env is one user-submitted URL away from
    leaking instance credentials.
    """
    with patch.object(
        socket, "getaddrinfo", return_value=_fake_getaddrinfo(internal_ip)
    ):
        with pytest.raises(ValueError) as excinfo:
            validate_url_not_internal(f"http://attacker-controlled.example/{label}")
        assert internal_ip in str(excinfo.value)


def test_validate_url_not_internal_silent_on_dns_failure():
    """``socket.gaierror`` (DNS resolution failed) -> swallow and
    return None. The actual outbound request will fail later with
    a clearer error; the validator's job is SSRF prevention, not
    URL-reachability checking.
    """
    with patch.object(socket, "getaddrinfo", side_effect=socket.gaierror("nope")):
        # Must NOT raise — falls through silently.
        assert validate_url_not_internal("https://nonexistent.invalid/path") is None


def test_validate_url_not_internal_silent_on_empty_url():
    """Empty / None URL -> nothing to validate. Common in optional
    URL fields that round-trip from forms.
    """
    assert validate_url_not_internal("") is None
    assert validate_url_not_internal(None) is None


def test_validate_url_not_internal_silent_on_no_hostname():
    """``mailto:foo@bar``, ``file:///``, and similar schemes have
    no hostname component. The validator can't resolve them, so
    it returns silently — the scheme-allowlist (separate function)
    is the right gate for those.
    """
    assert validate_url_not_internal("mailto:foo@bar.example") is None
    assert validate_url_not_internal("file:///etc/passwd") is None


def test_validate_url_not_internal_first_match_in_round_robin_rejects_all():
    """A hostname that resolves to MULTIPLE addresses (round-robin
    DNS, dual-stack) must reject if ANY of them is internal. This
    is the standard SSRF mitigation against attackers who set up
    a hostname to alternately resolve to a public IP (passing
    validation) and a private one (the SSRF target) — the request
    library may pick the second on retry.
    """
    mixed = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
    ]
    with patch.object(socket, "getaddrinfo", return_value=mixed):
        with pytest.raises(ValueError) as excinfo:
            validate_url_not_internal("http://dns-rebind-target.example")
        # The error names the actual offending IP, not just
        # "internal" — helpful for triage.
        assert "127.0.0.1" in str(excinfo.value)


# ─────────────────────────────────────────────────────────────────────
# validate_url_scheme
# ─────────────────────────────────────────────────────────────────────


def test_validate_url_scheme_allows_http_by_default():
    """Default allowlist is ``http``/``https``. Plain ``http://``
    must pass."""
    assert validate_url_scheme("http://example.com/path") is None


def test_validate_url_scheme_allows_https_by_default():
    assert validate_url_scheme("https://example.com/path") is None


@pytest.mark.parametrize(
    "scheme",
    [
        "javascript",
        "data",
        "file",
        "gopher",
        "ftp",
        "ldap",
        "dict",
    ],
)
def test_validate_url_scheme_rejects_dangerous_schemes(scheme):
    """Each scheme commonly abused for XSS or SSRF must be
    rejected when the default allowlist is in effect.

    ``javascript:`` and ``data:`` are XSS vectors when rendered;
    ``file:``, ``gopher:``, ``ftp:``, ``ldap:``, ``dict:`` are
    SSRF amplifiers (curl-equivalent libraries handle them).
    """
    with pytest.raises(ValueError) as excinfo:
        validate_url_scheme(f"{scheme}:something-here")
    # Error message names the rejected scheme so callers can
    # surface it to the user.
    assert scheme in str(excinfo.value).lower()


def test_validate_url_scheme_allows_custom_scheme_when_in_allowlist():
    """Callers can opt into additional schemes (e.g. ``mailto`` for
    a notification settings form). Pin so the override is honored.
    """
    # mailto is rejected by default, allowed when explicitly listed.
    with pytest.raises(ValueError):
        validate_url_scheme("mailto:foo@bar.example")
    assert (
        validate_url_scheme(
            "mailto:foo@bar.example", allowed_schemes=("http", "https", "mailto")
        )
        is None
    )


def test_validate_url_scheme_silent_on_empty_url():
    """Empty / None URL -> nothing to validate. Same defensive
    contract as ``validate_url_not_internal``.
    """
    assert validate_url_scheme("") is None
    assert validate_url_scheme(None) is None


def test_validate_url_scheme_silent_on_no_scheme():
    """A bare hostname (no ``scheme:``) returns silently — the
    parser yields an empty scheme and the ``if parsed.scheme``
    guard skips the allowlist check. This is intentional: callers
    that need to enforce a scheme should pre-prepend ``https://``.
    """
    assert validate_url_scheme("example.com/path") is None


def test_validate_url_scheme_strips_whitespace():
    """Trailing / leading whitespace must NOT bypass the allowlist
    via header smuggling (e.g. ``" javascript:..."``). The
    production code does ``url.strip()`` before parsing.
    """
    with pytest.raises(ValueError):
        validate_url_scheme("  javascript:alert(1)  ")


def test_validate_url_scheme_case_insensitive():
    """Schemes are compared case-insensitively (``JAVASCRIPT:``,
    ``Data:``, etc. all rejected). HTTP RFC says scheme is
    case-insensitive; pin so a future tightening that only checks
    lowercase doesn't open a bypass.
    """
    with pytest.raises(ValueError):
        validate_url_scheme("JAVASCRIPT:alert(1)")
    with pytest.raises(ValueError):
        validate_url_scheme("Data:text/html,<script>alert(1)</script>")
    # Valid schemes also respect case-insensitivity.
    assert validate_url_scheme("HTTPS://example.com") is None
