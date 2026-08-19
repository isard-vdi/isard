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

import requests

_REGISTER_TIMEOUT = 15
_REQUIRED = ("username", "password", "subdomain", "fulldomain")


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
