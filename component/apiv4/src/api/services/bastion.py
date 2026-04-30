#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Naomi Hidalgo Piñar
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

import os

from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.bastion import Bastion
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.models.targets import Targets


class BastionService:

    @staticmethod
    def get_desktop_bastion(desktop_id: str) -> dict:
        """
        Get the bastion target for a desktop.
        If no target exists, create an empty one.
        """
        try:
            target = Targets.get_domain_target(desktop_id)
        except Exception:
            target = Targets.update_domain_target(desktop_id, {})
        return target

    @staticmethod
    def update_desktop_bastion(
        desktop_id: str, data: dict, can_use_individual_domains: bool
    ) -> dict:
        """
        Update the bastion target for a desktop.
        If the user cannot use individual domains, the domain field is cleared.
        """
        if not can_use_individual_domains:
            data["domain"] = None

        Targets.update_domain_target(desktop_id, data)
        return {}

    @staticmethod
    def get_admin_bastion_config() -> dict:
        """
        Get the admin bastion configuration overview.
        """
        bastion_enabled_in_cfg = (
            os.environ.get("BASTION_ENABLED", "false").lower() == "true"
        )
        bastion_is_enabled = Helpers.bastion_enabled()
        bastion_domain = Bastion.get_bastion_domain()

        return {
            "bastion_enabled": bastion_is_enabled,
            "bastion_enabled_in_cfg": bastion_enabled_in_cfg,
            "bastion_enabled_in_db": Bastion.bastion_enabled_in_db(),
            "bastion_domain": bastion_domain,
            "bastion_ssh_port": (
                os.environ.get(
                    "BASTION_SSH_PORT",
                    os.environ.get("HTTPS_PORT", "443"),
                )
                if bastion_is_enabled
                else None
            ),
            "domain_verification_required": Bastion.bastion_domain_verification_required(),
        }

    @staticmethod
    def remove_disallowed_bastion_targets() -> list:
        """
        Remove bastion targets that are no longer allowed.
        """
        return Alloweds.remove_disallowed_bastion_targets()

    @staticmethod
    def update_bastion_config(
        enabled: bool,
        bastion_domain: str,
        domain_verification_required: bool,
    ) -> None:
        """
        Update the bastion configuration.
        """
        Bastion.update_bastion_config(
            enabled,
            bastion_domain,
            domain_verification_required,
        )

    @staticmethod
    def get_bastion_domain_verification_config() -> dict:
        """
        Get the bastion domain verification configuration.
        """
        return {
            "domain_verification_required": Bastion.bastion_domain_verification_required()
        }

    @staticmethod
    def update_bastion_authorized_keys(desktop_id: str, authorized_keys: list) -> dict:
        """Update SSH authorized keys for a desktop's bastion target."""
        if not authorized_keys:
            raise Error(
                "bad_request",
                "Authorized keys are required",
            )
        target = Targets.get_domain_target(desktop_id)
        ssh = target.get("ssh", {})
        ssh["authorized_keys"] = authorized_keys
        Targets.update_domain_target(desktop_id, {"ssh": ssh})
        return {}

    @staticmethod
    def update_bastion_domains(
        desktop_id: str,
        domains: list,
        category_id: str,
    ) -> dict:
        """Update custom domains for a desktop's bastion target with DNS verification."""
        # Filter empty/whitespace entries
        domains = [d.strip() for d in domains if d and d.strip()]

        if len(domains) > 10:
            raise Error(
                "bad_request",
                "Maximum 10 domains allowed",
            )

        target = Targets.get_domain_target(desktop_id)

        # Validate uniqueness (excluding current target)
        Bastion.check_duplicate_bastion_domains(domains, target_id=target["id"])

        # DNS verification and HAProxy management are handled inside
        # Targets.update_domain_target when "domains" key is present
        Targets.update_domain_target(desktop_id, {"domains": domains})
        return {}

    @staticmethod
    def verify_bastion_domain(
        desktop_id: str,
        domain: str,
        category_id: str,
    ) -> dict:
        """Verify a single domain's DNS without saving."""
        domain = domain.strip()
        if not domain:
            raise Error(
                "bad_request",
                "Domain is required",
            )

        target = Targets.get_domain_target(desktop_id)

        # Check for duplicates (excluding current target)
        Bastion.check_duplicate_bastion_domains([domain], target_id=target["id"])

        # Verify DNS
        if Bastion.bastion_domain_verification_required():
            bastion_domain = Bastion.get_bastion_domain(category_id)
            Bastion.check_bastion_domain_dns(
                domain,
                f"{target['id']}.{bastion_domain}",
                kind="cname",
            )

        return {"verified": True}
