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
"""Admin service for the deployment-wide main-domain certificate configuration.

Mirrors :class:`AdminViewersConfigService`: global, admin-only, and a thin
layer over an ``isardvdi_common`` accessor. It persists configuration only;
issuance is driven elsewhere.
"""

import copy

from isardvdi_common.helpers.certificates_config import CertificatesConfig

# Derived on read from certificate_source, never stored: it is a function of
# another persisted field, so writing it would create a second source of truth
# that can disagree with the first.
_CHALLENGE_BY_SOURCE = {"acme": "http-01"}


def _derive_main_domain_challenge(certs: dict) -> dict:
    """Set the display-only ``main_domain.acme_challenge`` from the source."""
    main = (certs or {}).get("main_domain")
    if not isinstance(main, dict):
        return certs
    challenge = _CHALLENGE_BY_SOURCE.get(main.get("certificate_source"))
    if challenge:
        main["acme_challenge"] = challenge
    return certs


def _merge_main_domain(new_certs: dict, existing_certs: dict) -> dict:
    """Return the full document to persist, merged over what is stored.

    Two things make this necessary rather than optional. The route builds its
    payload with ``model_dump(exclude_none=True)``, so a field the admin form
    does not render is simply absent; and the write goes through
    ``replace_certificates_config``, which uses ``r.literal`` and therefore
    deletes every key it is not handed. Without this merge, saving the domain
    name alone would silently discard the ACME account e-mail and server.

    ``acme_challenge`` is dropped from both sides, so a value that reached the
    database before it was display-only does not survive a round trip.
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

    return merged


class AdminCertificatesService:
    """Global (admin-only) main-domain certificate configuration."""

    @staticmethod
    def get_certificates() -> dict:
        """Return ``config[1].certificates`` with the challenge derived."""
        certs = CertificatesConfig.get_certificates_config()
        _derive_main_domain_challenge(certs)
        return certs

    @staticmethod
    def update_certificates(data: dict) -> None:
        """Persist the main-domain certificate config over what is stored."""
        existing = CertificatesConfig.get_certificates_config()
        CertificatesConfig.replace_certificates_config(
            _merge_main_domain(data, existing)
        )
