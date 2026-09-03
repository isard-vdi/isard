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
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.models.targets import Targets


class BastionService:
    @staticmethod
    def apply_bastion_config(desktop_id: str, config: dict) -> None:
        """Apply a bastion config (ssh/http enable + ports) to a desktop's
        target, **preserving** existing authorized_keys / domains. Creates the
        target if missing. Writes only when something changed.

        ``config`` shape: ``{"ssh": {"enabled", "port"}, "http": {"enabled",
        "http_port", "https_port"}}``. Used both by the deployment-level apply
        (over all desktops) and by the at-start reconcile.
        """
        ssh_cfg = (config or {}).get("ssh") or {}
        http_cfg = (config or {}).get("http") or {}
        try:
            target = Targets.get_domain_target(desktop_id)
            exists = True
        except Error as exc:
            if getattr(exc, "status_code", None) != 404:
                raise
            target = {}
            exists = False
        cur_ssh = dict(target.get("ssh") or {})
        cur_http = dict(target.get("http") or {})
        new_ssh = {
            **cur_ssh,
            "enabled": bool(ssh_cfg.get("enabled")),
            "port": int(ssh_cfg.get("port", cur_ssh.get("port", 22))),
        }
        new_ssh.setdefault("authorized_keys", cur_ssh.get("authorized_keys", []))
        new_http = {
            **cur_http,
            "enabled": bool(http_cfg.get("enabled")),
            "http_port": int(http_cfg.get("http_port", cur_http.get("http_port", 80))),
            "https_port": int(
                http_cfg.get("https_port", cur_http.get("https_port", 443))
            ),
        }
        if exists and new_ssh == cur_ssh and new_http == cur_http:
            return
        Targets.update_domain_target(desktop_id, {"ssh": new_ssh, "http": new_http})

    @staticmethod
    def _get_desktop_deployment_bastion(desktop_id: str):
        """Return the bastion config of the desktop's deployment, or None when
        it is not in a deployment (or the deployment has no bastion config).

        Deployment membership is the ``domains.tag`` field == deployment id.
        Tolerant: a missing domain/deployment doc (Caches raises ValueError)
        yields None.
        """
        try:
            tag = Caches.get_document("domains", desktop_id, ["tag"])
        except ValueError:
            return None
        if not tag:
            return None
        try:
            deployment = Caches.get_document("deployments", tag)
        except ValueError:
            return None
        if not deployment:
            return None
        return deployment.get("bastion")

    @staticmethod
    def ensure_bastion_config_on_start(desktop_id: str) -> None:
        """At desktop start: reconcile a deployment desktop's bastion target to
        its deployment's bastion config.

        This is how recreated/new deployment desktops inherit bastion (and get a
        target at all) on their first start. No-op for desktops outside a
        deployment or whose deployment has no bastion config.

        No key material is written here: the bastion resolves the desktop
        owner's and the deployment owner/co-owners' profile keys live at SSH
        connection time.
        """

        dep_bastion = BastionService._get_desktop_deployment_bastion(desktop_id)

        if dep_bastion:
            BastionService.apply_bastion_config(desktop_id, dep_bastion)

    @staticmethod
    def get_desktop_bastion_active(desktop_id: str) -> dict:
        """Read-only check for the desktop-card 'Bastion' entry.

        Unlike :meth:`get_desktop_bastion` this never creates a target, so it
        can be called lazily on click for any desktop. Returns whether SSH/HTTP
        bastion access is enabled plus the data needed to render the read-only
        access links.
        """
        try:
            target = Targets.get_domain_target(desktop_id)
        except Error as exc:
            if getattr(exc, "status_code", None) == 404:
                return {
                    "exists": False,
                    "ssh": {"enabled": False, "port": 22},
                    "http": {"enabled": False, "http_port": 80, "https_port": 443},
                }
            raise
        cfg = BastionService.get_admin_bastion_config()
        ssh = target.get("ssh") or {}
        http = target.get("http") or {}
        return {
            "exists": True,
            "id": target.get("id"),
            "domains": target.get("domains", []),
            "ssh": {
                "enabled": bool(ssh.get("enabled")),
                "port": ssh.get("port", 22),
            },
            "http": {
                "enabled": bool(http.get("enabled")),
                "http_port": http.get("http_port", 80),
                "https_port": http.get("https_port", 443),
            },
            "bastion_domain": cfg.get("bastion_domain"),
            "bastion_ssh_port": cfg.get("bastion_ssh_port"),
            "bastion_enabled": cfg.get("bastion_enabled"),
        }

    @staticmethod
    def build_target_urls(target: dict, bastion_domain: str, ssh_port) -> dict:
        """Build the public bastion connection URLs for a target document.

        Without a custom domain, HTTP(S) is served on a per-target subdomain of
        the bastion domain (the target id with its last "-" turned into "."),
        reachable on the platform's public web ports.
        """
        ssh = (target or {}).get("ssh") or {}
        http = (target or {}).get("http") or {}
        target_id = (target or {}).get("id", "")
        custom_domains = (target or {}).get("domains") or []
        custom_domain = custom_domains[0] if custom_domains else ""
        host = custom_domain or bastion_domain or ""
        target_host = (
            f"{'.'.join(target_id.rsplit('-', 1))}.{bastion_domain}"
            if target_id and not custom_domain
            else host
        )
        ssh_command = ""
        if ssh.get("enabled") and target_id:
            port = "" if str(ssh_port) == "22" else f" -p {ssh_port}"
            ssh_command = f"ssh {target_id}@{host}{port}"
        http_url = https_url = ""
        if http.get("enabled"):
            http_p = os.environ.get("HTTP_PORT", "80")
            https_p = os.environ.get("HTTPS_PORT", "443")
            http_url = f"http://{target_host}" + (
                "" if str(http_p) == "80" else f":{http_p}"
            )
            https_url = f"https://{target_host}" + (
                "" if str(https_p) == "443" else f":{https_p}"
            )
        return {
            "target_id": target_id,
            "custom_domain": custom_domain,
            "custom_domains": custom_domains,
            "ssh_enabled": bool(ssh.get("enabled")),
            "ssh_command": ssh_command,
            "http_enabled": bool(http.get("enabled")),
            "http_url": http_url,
            "https_url": https_url,
        }

    @staticmethod
    def get_desktop_bastion_direct_viewer(desktop_id: str) -> dict:
        """Read-only bastion access info for the direct viewer.

        Like :meth:`get_desktop_bastion_active` this never creates a target.
        ``enabled`` is False whenever there is nothing to show.
        """
        cfg = BastionService.get_admin_bastion_config()
        if not cfg.get("bastion_enabled"):
            return {"enabled": False}
        try:
            target = Targets.get_domain_target(desktop_id)
        except Error as exc:
            if getattr(exc, "status_code", None) == 404:
                return {"enabled": False}
            raise
        urls = BastionService.build_target_urls(
            target, cfg.get("bastion_domain"), cfg.get("bastion_ssh_port")
        )
        if not (urls["ssh_enabled"] or urls["http_enabled"]):
            return {"enabled": False}
        return {
            "enabled": True,
            "id": urls["target_id"] or None,
            "custom_domains": urls["custom_domains"],
            "ssh_enabled": urls["ssh_enabled"],
            "ssh_command": urls["ssh_command"] or None,
            "http_enabled": urls["http_enabled"],
            "http_url": urls["http_url"] or None,
            "https_url": urls["https_url"] or None,
        }

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
        If the user cannot use individual domains, the domains are cleared.
        """
        if not can_use_individual_domains:
            data["domains"] = []

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
        """Replace the "other people's" SSH keys for a desktop's bastion target.

        The list is stored verbatim (blank entries dropped, duplicates removed,
        order kept); an empty list simply means "no other keys". Nobody's
        profile key belongs here — the bastion resolves the desktop owner's and
        the deployment owner/co-owners' keys live at connection time.

        Raises 404 when the desktop has no bastion target; unlike
        ``Targets.update_domain_target`` this never creates one. Writes only
        when the list actually changes.
        """
        target = Targets.get_domain_target(desktop_id)
        # Merge into the stored ssh subdocument: update_domain_target *replaces*
        # target["ssh"] wholesale, so sending only authorized_keys would drop
        # enabled/port and silently turn SSH off.
        ssh = dict(target.get("ssh") or {})
        original = list(ssh.get("authorized_keys") or [])

        keys = []
        for key in authorized_keys or []:
            if not isinstance(key, str) or not key.strip():
                continue
            key = key.strip()
            if key not in keys:
                keys.append(key)

        if keys != original:
            ssh["authorized_keys"] = keys
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
