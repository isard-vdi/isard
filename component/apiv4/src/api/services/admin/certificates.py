#
#   Copyright © 2026 Josep Maria Viñolas Auquer
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Admin service for the deployment-wide main-domain certificate configuration."""

import copy
import logging as log
import threading
import traceback

from api.services.error import Error
from isardvdi_common.helpers.bastion import Bastion
from isardvdi_common.helpers.certificates_config import CertificatesConfig

# Derived on read from certificate_source, never stored (single source of truth).
_CHALLENGE_BY_SOURCE = {"acme": "http-01", "acme_dns": "dns-01"}


def _derive_main_domain_challenge(certs: dict) -> dict:
    """Set the display-only ``main_domain.acme_challenge`` from the source."""
    main = (certs or {}).get("main_domain")
    if not isinstance(main, dict):
        return certs
    challenge = _CHALLENGE_BY_SOURCE.get(main.get("certificate_source"))
    if challenge:
        main["acme_challenge"] = challenge
    return certs


def _strip_main_domain_secret(certs: dict) -> dict:
    """Replace the stored acme-dns password with a flag saying one exists.

    The credentials live in the database in the clear, like the rest of this
    product's. Returning one in a GET is a different exposure: it lands in the
    browser's history and in the logs of whatever proxies the call, which are
    places the others do not reach. The form is told whether a password is
    stored so it can say "leave blank to keep it" rather than guessing.

    Operates on a copy. The document this is handed comes from a cache, and
    emptying the password in place would take it away from the issuance path
    that reads the same entry.
    """
    main = (certs or {}).get("main_domain")
    if not isinstance(main, dict):
        return certs

    acmedns = main.get("acmedns")
    if not isinstance(acmedns, dict):
        return certs

    acmedns = dict(acmedns)
    acmedns["password_set"] = bool(acmedns.pop("password", None))
    main = dict(main)
    main["acmedns"] = acmedns
    certs = dict(certs)
    certs["main_domain"] = main
    return certs


def _preserve_main_domain_secret(new_certs: dict, existing_certs: dict) -> None:
    """Keep the stored acme-dns password when the payload leaves it blank.

    The other half of never returning it: the form cannot resend a value it was
    never given, and the write replaces the whole subtree, so a blank would
    destroy the credential on any save that touched anything else.

    Blank with nothing stored is the case the two existing helpers for
    authentication secrets disagree about -- one raises as required, the other
    drops the key and says nothing. This field is the required kind: without a
    password there is no issuance at all, so accepting the save would store a
    configuration that cannot work and report success. Only when the source is
    actually acme_dns, so a deployment on HTTP-01 is never asked for one.
    """
    new_main = (new_certs or {}).get("main_domain")
    if not isinstance(new_main, dict):
        return

    acmedns = new_main.get("acmedns")
    if not isinstance(acmedns, dict):
        return

    if "password" not in acmedns:
        return
    if acmedns["password"]:
        return

    existing_main = (existing_certs or {}).get("main_domain")
    stored = None
    if isinstance(existing_main, dict) and isinstance(
        existing_main.get("acmedns"), dict
    ):
        stored = existing_main["acmedns"].get("password")

    if stored:
        acmedns["password"] = stored
        return

    source = new_main.get("certificate_source")
    if source is None and isinstance(existing_main, dict):
        source = existing_main.get("certificate_source")

    if source == "acme_dns":
        raise Error(
            "bad_request",
            "an acme-dns password is required",
            description_code="acmedns_password_required",
        )

    acmedns.pop("password")


def _merge_main_domain(new_certs: dict, existing_certs: dict) -> dict:
    """Return the full document to persist, merged over what is stored.

    Necessary because the route sends only rendered fields (``exclude_none``) and
    the write uses ``r.literal`` (deletes unsent keys); without merging, saving
    one field discards the rest. ``acme_challenge`` is dropped, being display-only.
    """
    merged = copy.deepcopy(existing_certs or {})
    incoming = copy.deepcopy(new_certs or {})

    for key, value in incoming.items():
        if key == "main_domain" and isinstance(value, dict):
            main = merged.get("main_domain")
            main = dict(main) if isinstance(main, dict) else {}
            main.update(value)
            merged["main_domain"] = main
        else:
            merged[key] = value

    main = merged.get("main_domain")
    if isinstance(main, dict):
        main.pop("acme_challenge", None)

        # The acme-dns block merges field by field for the same reason the
        # main-domain block does: the form does not render all of it, and the
        # write drops every key it is not handed.
        incoming_main = (new_certs or {}).get("main_domain")
        if isinstance(incoming_main, dict) and isinstance(
            incoming_main.get("acmedns"), dict
        ):
            existing_main = (existing_certs or {}).get("main_domain")
            base = {}
            if isinstance(existing_main, dict) and isinstance(
                existing_main.get("acmedns"), dict
            ):
                base = dict(existing_main["acmedns"])
            base.update(incoming_main["acmedns"])
            base.pop("password_set", None)
            main["acmedns"] = base

    return merged


def _issue_main_domain_now() -> None:
    """Run the issuance and swallow errors: the config is already saved, so a
    failure here is not a failed save and there is nobody to return it to."""
    try:
        Bastion.issue_main_domain_certificate()
    except Exception:
        log.warning(
            "Main-domain certificate issuance failed:\n" + traceback.format_exc()
        )


def _dispatch_main_domain_issuance() -> None:
    """Start the issuance in a daemon thread, off the request path: a CA round
    trip regularly outlives the gRPC retry budget, which would stall an admin
    save or apiv4 startup. The work is idempotent and observable through the GET.
    """
    threading.Thread(
        target=_issue_main_domain_now,
        name="issue-main-domain-certificate",
        daemon=True,
    ).start()


class AdminCertificatesService:
    """Global (admin-only) main-domain certificate configuration."""

    @staticmethod
    def get_certificates() -> dict:
        """Return ``config[1].certificates`` with the challenge derived."""
        certs = CertificatesConfig.get_certificates_config()
        certs = _strip_main_domain_secret(certs)
        _derive_main_domain_challenge(certs)
        return certs

    @staticmethod
    def update_certificates(data: dict) -> None:
        """Persist the main-domain certificate config over what is stored."""
        existing = CertificatesConfig.get_certificates_config()
        _preserve_main_domain_secret(data, existing)
        CertificatesConfig.replace_certificates_config(
            _merge_main_domain(data, existing)
        )
        # Off the request path on purpose: see _dispatch_main_domain_issuance.
        _dispatch_main_domain_issuance()
