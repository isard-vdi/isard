#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 IsardVDI
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Client for an acme-dns server (DNS-01 challenge)."""

import os

import dns.name
import dns.resolver
import requests

_REGISTER_TIMEOUT = 15
_REQUIRED = ("username", "password", "subdomain", "fulldomain")

_CHALLENGE_PREFIX = "_acme-challenge"
_VERIFY_TIMEOUT = 5.0
_NAMESERVERS_ENV = "ACMEDNS_VERIFY_NAMESERVERS"
# Fallback only: a resolver serving a private view of the zone will not have
# the record the certificate authority asks a public one for.
_PUBLIC_FALLBACK = ("1.1.1.1", "8.8.8.8")


class AcmeDnsError(Exception):
    pass


def register(base_url: str) -> dict:
    """Register a fresh account and return its credentials.

    No allowfrom is sent on purpose: our acme-dns reads the client address from
    X-Forwarded-For (use_header) and the proxy does not set it, so an allowfrom
    would 401 every caller.

    Every call creates a NEW account (acme-dns has no update or delete), so
    callers must refuse to overwrite credentials already in use: a second
    registration strands the first account and invalidates the CNAME created
    for it.
    """
    if not base_url:
        raise AcmeDnsError("an acme-dns server URL is required to register")

    server = base_url.rstrip("/")
    url = f"{server}/register"

    try:
        response = requests.post(url, timeout=_REGISTER_TIMEOUT)
        response.raise_for_status()
    except Exception:
        # No exception text: this response body carries the password on success.
        raise AcmeDnsError(
            f"could not register an account with the acme-dns server at {server}. "
            "Check the URL is right and that this deployment can reach it."
        )

    try:
        data = response.json()
    except Exception:
        raise AcmeDnsError(
            f"the acme-dns server at {server} did not answer with JSON. "
            "Check the URL points at an acme-dns server."
        )

    missing = [field for field in _REQUIRED if not (data or {}).get(field)]
    if missing:
        raise AcmeDnsError(
            f"the acme-dns server at {server} returned an incomplete "
            f"registration, missing: {', '.join(missing)}"
        )

    return {
        "base_url": server,
        "username": data["username"],
        "password": data["password"],
        "subdomain": data["subdomain"],
        "fulldomain": data["fulldomain"],
    }


def _configured_nameservers() -> list:
    raw = os.environ.get(_NAMESERVERS_ENV, "")
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def _resolve_cname(record: str, nameservers) -> str:
    """Return the CNAME target seen by one resolver, or None. nameservers=None
    uses the system resolver (/etc/resolv.conf), the only one that works under
    filtered egress.
    """
    resolver = dns.resolver.Resolver()
    if nameservers:
        resolver.nameservers = list(nameservers)
    resolver.timeout = _VERIFY_TIMEOUT
    resolver.lifetime = _VERIFY_TIMEOUT

    try:
        answer = resolver.resolve(record, "CNAME")
    except Exception:
        # Any failure means "not visible from this resolver".
        return None

    for value in answer:
        return value.to_text().rstrip(".")
    return None


def verify_cname(domain: str, fulldomain: str) -> dict:
    """Report whether the challenge delegation for ``domain`` is in place and
    which resolver saw it; a negative is never authoritative (a CA queries the
    public internet, we do not).

    The system resolver is tried first (a pinned public one reports "not
    visible" forever under filtered egress); a public resolver only as a
    fallback on a negative. Explicit nameservers turn both off.
    """
    if not domain:
        raise AcmeDnsError("a domain is required to check the delegation")
    if not fulldomain:
        raise AcmeDnsError(
            "there are no acme-dns credentials to check this delegation against"
        )

    record = f"{_CHALLENGE_PREFIX}.{domain}"
    expected = dns.name.from_text(fulldomain).canonicalize()

    configured = _configured_nameservers()
    attempts = (
        [(configured, ",".join(configured))] if configured else [(None, "system")]
    )
    if not configured:
        attempts.append((_PUBLIC_FALLBACK, ",".join(_PUBLIC_FALLBACK)))

    observed = None
    # observed_by: the resolver that actually answered (set only if one did).
    # tried: where we looked, reported when nobody answered.
    observed_by = None
    tried = attempts[-1][1]
    for nameservers, label in attempts:
        seen = _resolve_cname(record, nameservers)
        if seen is None:
            continue
        observed = seen
        observed_by = label
        if dns.name.from_text(seen).canonicalize() == expected:
            return {
                "verified": True,
                "observed": seen,
                "expected": fulldomain.rstrip("."),
                "resolver": label,
                "message": f"{record} points at {seen}",
            }

    expected_text = fulldomain.rstrip(".")
    resolver_used = observed_by or tried
    if observed is not None:
        message = (
            f"{record} points at {observed}, not at {expected_text}. "
            "This usually means the delegation was created for an earlier "
            "acme-dns registration; it has to be changed, waiting will not "
            "fix it."
        )
    else:
        message = (
            f"{record} is not visible from {resolver_used} yet. Create it as a "
            f"CNAME pointing at {expected_text} and check again in a few "
            "minutes; DNS propagation can take a while."
        )

    return {
        "verified": False,
        "observed": observed,
        "expected": expected_text,
        "resolver": resolver_used,
        "message": message,
    }
