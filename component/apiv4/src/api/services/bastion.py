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
from isardvdi_common.models.user import User as RethinkUser


class BastionService:

    @staticmethod
    def _get_user_bastion_key(user_id) -> str | None:
        """Return the profile bastion SSH key of a user, or None.

        Tolerant: missing user / missing field / blank value all yield None
        so callers never have to special-case them.
        """
        if not user_id or not RethinkUser.exists(user_id):
            return None
        key = RethinkUser(user_id).bastion_ssh_key
        if isinstance(key, str) and key.strip():
            return key.strip()
        return None

    @staticmethod
    def normalize_authorized_keys(
        desktop_id: str,
        other_keys=None,
        ensure_user_ids=(),
        strip_user_ids=(),
    ) -> list:
        """Re-assert the owner-first authorized_keys convention on a target.

        Resulting list = ``[owner_profile_key?] + [ensured users' keys] +
        other_keys`` with every entry unique. ``other_keys`` are the manually
        managed "other people's" keys; when None the target's current keys are
        kept as the body. Profile keys of ``strip_user_ids`` are removed from
        the body (without being re-added unless they are also owner/ensured) —
        used to drop the editor's own key on save. Writes only when the list
        actually changes.
        """
        target = Targets.get_domain_target(desktop_id)
        ssh = dict(target.get("ssh") or {})
        original = list(ssh.get("authorized_keys") or [])

        owner_key = BastionService._get_user_bastion_key(target.get("user_id"))

        ensure_keys = []
        for uid in ensure_user_ids:
            key = BastionService._get_user_bastion_key(uid)
            if key and key not in ensure_keys:
                ensure_keys.append(key)

        strip_keys = set()
        for uid in strip_user_ids:
            key = BastionService._get_user_bastion_key(uid)
            if key:
                strip_keys.add(key)

        front = []
        managed = set()
        if owner_key:
            front.append(owner_key)
            managed.add(owner_key)
        for key in ensure_keys:
            if key not in managed:
                front.append(key)
                managed.add(key)

        body = original if other_keys is None else other_keys
        body = [k.strip() for k in body if isinstance(k, str) and k.strip()]

        seen = set(managed) | strip_keys
        rest = []
        for key in body:
            if key not in seen:
                rest.append(key)
                seen.add(key)

        new_list = front + rest
        if new_list != original:
            ssh["authorized_keys"] = new_list
            Targets.update_domain_target(desktop_id, {"ssh": ssh})
        return new_list

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
    def _get_desktop_deployment(desktop_id: str):
        """Return ``(owner_id, co_owner_ids, bastion_config)`` for the desktop's
        deployment, or ``(None, [], None)`` when it is not in a deployment.

        Deployment membership is the ``domains.tag`` field == deployment id.
        Tolerant: a missing domain/deployment doc (Caches raises ValueError)
        yields the "no deployment" tuple.
        """
        try:
            tag = Caches.get_document("domains", desktop_id, ["tag"])
        except ValueError:
            return None, [], None
        if not tag:
            return None, [], None
        try:
            deployment = Caches.get_document("deployments", tag)
        except ValueError:
            return None, [], None
        if not deployment:
            return None, [], None
        return (
            deployment.get("user"),
            deployment.get("co_owners") or [],
            deployment.get("bastion"),
        )

    @staticmethod
    def ensure_keys_on_start(desktop_id: str, actor_user_id) -> None:
        """At desktop start: reconcile a deployment desktop's bastion config and
        inject the relevant profile keys, re-asserting the owner-first convention.

        - If the desktop belongs to a deployment that has a bastion config, the
          target is reconciled to it first (this is how recreated/new deployment
          desktops inherit bastion on their first start).
        - Injects the desktop owner (index 0, via normalize), the acting user,
          and — for deployment desktops — the deployment owner + co-owners.
        - No-op when the (post-reconcile) target has no SSH bastion enabled.

        ``actor_user_id`` is whoever performs the start (owner, or an
        admin/manager/advanced user starting someone else's desktop).
        """
        dep_owner, dep_co_owners, dep_bastion = BastionService._get_desktop_deployment(
            desktop_id
        )

        if dep_bastion:
            BastionService.apply_bastion_config(desktop_id, dep_bastion)

        try:
            target = Targets.get_domain_target(desktop_id)
        except Error as exc:
            if getattr(exc, "status_code", None) == 404:
                return
            raise
        if not (target.get("ssh") or {}).get("enabled"):
            return

        ensure_user_ids = [actor_user_id] if actor_user_id else []
        if dep_owner and dep_owner not in ensure_user_ids:
            ensure_user_ids.append(dep_owner)
        for co_owner in dep_co_owners:
            if co_owner not in ensure_user_ids:
                ensure_user_ids.append(co_owner)

        BastionService.normalize_authorized_keys(
            desktop_id,
            other_keys=None,
            ensure_user_ids=ensure_user_ids,
        )

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
    def update_bastion_authorized_keys(
        desktop_id: str, authorized_keys: list, editor_user_id=None
    ) -> dict:
        """Replace the "other people's" SSH keys for a desktop's bastion target.

        The desktop owner's profile key is managed automatically: it is stripped
        from the incoming list and re-prepended at index 0. The editor's own
        profile key is likewise stripped (it is managed through their profile,
        not this box). The frontend therefore only submits other people's keys;
        an empty list simply means "no other keys".
        """
        BastionService.normalize_authorized_keys(
            desktop_id,
            other_keys=authorized_keys or [],
            strip_user_ids=[editor_user_id] if editor_user_id else [],
        )
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
