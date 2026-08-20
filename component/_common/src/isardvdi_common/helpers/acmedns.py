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

"""Client for an acme-dns server.

An HTTP-01 challenge needs the name being certified to resolve to this
deployment and to be reachable on port 80. A DNS-01 challenge does not, which
is the whole point: it is the only way to certify a name that is not pointed
here yet, or that is served from behind something we do not control.

The awkward part of DNS-01 is that it wants write access to the customer's
zone, and nobody sensible hands that over for a certificate. acme-dns is the
usual way out: it is a tiny authoritative server that gives out a throwaway
subdomain plus credentials that can write one TXT record under it, and nothing
else. The customer delegates _acme-challenge.<their domain> to that subdomain
with a single CNAME, once, and every renewal after that is unattended.

So the credentials here are deliberately low-value: worst case someone writes a
TXT record under a random subdomain of our own acme-dns server. They are not a
key to the customer's DNS.
"""

import os

import dns.name
import dns.resolver
import requests

_REGISTER_TIMEOUT = 15
_REQUIRED = ("username", "password", "subdomain", "fulldomain")

_CHALLENGE_PREFIX = "_acme-challenge"
_VERIFY_TIMEOUT = 5.0
_NAMESERVERS_ENV = "ACMEDNS_VERIFY_NAMESERVERS"
# Tried only when the system resolver cannot see the delegation, and only
# because a resolver serving a private view of the zone will not have the
# record the certificate authority is going to ask a public one for.
_PUBLIC_FALLBACK = ("1.1.1.1", "8.8.8.8")


class AcmeDnsError(Exception):
    """Something went wrong talking to the acme-dns server."""


def register(base_url: str) -> dict:
    """Register a fresh account and return its credentials.

    No allowfrom is sent, and that is deliberate rather than an oversight.
    acme-dns can restrict an account to a list of source addresses, but ours
    runs with use_header set to read the client address from X-Forwarded-For,
    and the proxy in front of it does not add that header. The address it
    compares against is therefore never the caller's, so an account registered
    with an allowfrom answers 401 from every address including the right one --
    credentials that look correct and can never issue anything.

    What is left protecting the account is the random username and the
    forty-character password, and the fact that the account can write exactly
    one TXT record under one throwaway subdomain of our own server.

    Every call creates a NEW account: acme-dns has no update and no delete.
    Registering a second time for a name that already has credentials strands
    the first account and, worse, invalidates the CNAME the customer has
    already created -- so callers must refuse to overwrite credentials in use
    rather than relying on this function to notice.
    """
    if not base_url:
        raise AcmeDnsError("an acme-dns server URL is required to register")

    server = base_url.rstrip("/")
    url = f"{server}/register"

    try:
        response = requests.post(url, timeout=_REGISTER_TIMEOUT)
        response.raise_for_status()
    except Exception:
        # Deliberately not including the exception text: on the success path
        # this response body carries the password, and an error message is the
        # one place it would be written down.
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
        # Storing a partial registration is worse than failing here: it yields
        # a CNAME instruction the operator passes on to the customer, and the
        # gap only shows up at issuance, long after anyone is still watching.
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
    """Nameservers the operator named, if any."""
    raw = os.environ.get(_NAMESERVERS_ENV, "")
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def _resolve_cname(record: str, nameservers) -> str:
    """Return the CNAME target seen by one resolver, or None.

    ``nameservers`` of None means the system resolver: dns.resolver.Resolver()
    reads /etc/resolv.conf, which is the behaviour this deployment is
    configured for and the only one that works when egress is filtered.
    """
    resolver = dns.resolver.Resolver()
    if nameservers:
        resolver.nameservers = list(nameservers)
    resolver.timeout = _VERIFY_TIMEOUT
    resolver.lifetime = _VERIFY_TIMEOUT

    try:
        answer = resolver.resolve(record, "CNAME")
    except Exception:
        # Every failure here means the same thing to the caller: this resolver
        # could not tell us. Missing, refused, timed out and misconfigured all
        # end up as "not visible from here", which is what gets reported.
        return None

    for value in answer:
        return value.to_text().rstrip(".")
    return None


def verify_cname(domain: str, fulldomain: str) -> dict:
    """Report whether the challenge delegation for ``domain`` is in place.

    The answer that actually matters is the one a certificate authority will
    get from the public internet, and we are not sitting there. So this reports
    what it saw and which resolver saw it, and never presents a negative as
    authoritative.

    The system resolver is asked first, deliberately. Pinning a public resolver
    and skipping /etc/resolv.conf reports "not visible" forever on any
    deployment with filtered egress -- indistinguishable, from the operator's
    side, from a CNAME nobody has created yet. A public resolver is tried only
    afterwards and only on a negative, because a resolver serving a private
    view of the zone will not hold the record the authority is going to ask
    for. Naming resolvers explicitly turns both of those off: an operator who
    names one means that one.

    A record aimed at the wrong target is reported as such rather than as a
    missing one. Both block issuance, but waiting fixes a missing record and
    never fixes a delegation pointing at a registration that has been replaced.
    """
    if not domain:
        raise AcmeDnsError("a domain is required to check the delegation")
    if not fulldomain:
        # Without it there is nothing to compare against, and a check that
        # cannot fail would report every domain as ready to issue.
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
    # Two labels, because they answer different questions. observed_by names
    # the resolver whose answer is being reported, and only a resolver that
    # actually answered can be it: attributing one resolver's observation to
    # another destroys the only thing having two of them buys. tried is where
    # it was looked for, which is what to report when nobody saw anything.
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
