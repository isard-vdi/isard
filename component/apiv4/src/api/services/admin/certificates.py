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
from isardvdi_common.helpers import acmedns
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
    """Replace the stored acme-dns password with a password_set flag for GET
    responses; the password is never returned.

    Operates on a copy: the document comes from a shared cache, and emptying the
    password in place would take it from the issuance path reading the same entry.
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
    """Keep the stored acme-dns password when the payload leaves it blank: the
    form cannot resend a value it never received, and the write replaces the
    whole subtree, so a blank would otherwise destroy the credential.

    Blank with nothing stored raises, but only when the source is acme_dns:
    without a password issuance cannot work, so the save must not report success.
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

        # Field-by-field merge: the form does not render the whole acme-dns
        # block, and the write drops every key it is not handed.
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


def _main_domain_name(certs: dict) -> str:
    """The name the delegation has to be created for."""
    main = (certs or {}).get("main_domain") or {}
    names = main.get("names") or []
    return names[0] if names else ""


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

    @staticmethod
    def register_acmedns(base_url: str, replace: bool = False) -> dict:
        """Register a fresh acme-dns account for the main domain. Refuses to
        overwrite stored credentials unless replace is set (see acmedns.register
        on why a second registration cannot be undone).
        """
        certs = CertificatesConfig.get_certificates_config()
        name = _main_domain_name(certs)
        if not name:
            raise Error(
                "bad_request",
                "configure the certificate name before registering an acme-dns account",
                description_code="acmedns_name_required",
            )

        main = (certs or {}).get("main_domain") or {}
        stored = main.get("acmedns") or {}
        if stored.get("username") and not replace:
            raise Error(
                "bad_request",
                "an acme-dns account is already registered for this domain. "
                "Registering another one abandons it, and any CNAME already "
                "created for it stops working.",
                description_code="acmedns_already_registered",
            )

        try:
            credentials = acmedns.register(base_url)
        except acmedns.AcmeDnsError as exc:
            raise Error(
                "internal_server",
                str(exc),
                description_code="acmedns_register_failed",
            )

        # verified reset to false: the account is new, nothing is delegated yet;
        # a stale true would let issuance run against a missing record.
        AdminCertificatesService.update_certificates(
            {
                "main_domain": {
                    "certificate_source": "acme_dns",
                    "acmedns": dict(credentials, auto_register=True, verified=False),
                }
            }
        )

        return {
            "cname_record": f"_acme-challenge.{name}",
            "cname_target": credentials["fulldomain"],
            "username": credentials["username"],
            "subdomain": credentials["subdomain"],
            "fulldomain": credentials["fulldomain"],
            "password_set": True,
        }

    @staticmethod
    def verify_acmedns() -> dict:
        """Check the delegation and record whether it is in place.

        Negative is returned, not raised (polled while DNS propagates). The flag
        is written in both directions: a stale true would let issuance run
        against a delegation that is no longer there.
        """
        certs = CertificatesConfig.get_certificates_config()
        name = _main_domain_name(certs)
        main = (certs or {}).get("main_domain") or {}
        fulldomain = (main.get("acmedns") or {}).get("fulldomain")

        if not name or not fulldomain:
            raise Error(
                "bad_request",
                "there is no acme-dns registration to check a delegation against",
                description_code="acmedns_not_registered",
            )

        result = acmedns.verify_cname(name, fulldomain)

        AdminCertificatesService.update_certificates(
            {"main_domain": {"acmedns": {"verified": bool(result["verified"])}}}
        )

        return result
