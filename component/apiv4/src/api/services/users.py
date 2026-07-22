#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
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

import base64
import os
import struct
import time

import bcrypt
from api.services.error import Error
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.isard_vpn import IsardVpn
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.helpers.user_storage import UserStorage
from isardvdi_common.lib.domains.desktops.desktops import (
    DesktopsProcessed as CommonDesktops,
)
from isardvdi_common.lib.domains.domains import DomainsProcessed
from isardvdi_common.lib.users.groups.groups import GroupsProcessed as CommonGroups
from isardvdi_common.lib.users.users.user import UsersProcessed as CommonUser
from isardvdi_common.lib.users.users.user_policies import (
    UserPolicies as CommonUserPolicies,
)
from isardvdi_common.models.category import Category as RethinkCategory
from isardvdi_common.models.group import Group as RethinkGroup
from isardvdi_common.models.roles import Roles as RethinkRole
from isardvdi_common.models.user import User as RethinkUser

# SSH public-key types accepted for a user's bastion key. Mirrors the set
# the bastion gateway (golang.org/x/crypto/ssh) understands, so a key that
# passes here will also be accepted by `ssh.ParseAuthorizedKey` there.
_SSH_KEY_TYPES = {
    "ssh-ed25519",
    "ssh-rsa",
    "ssh-dss",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
}


def validate_ssh_public_key(key: str) -> str:
    """Validate a single SSH public key and return it normalized (one line).

    Dependency-free check equivalent to `ssh.ParseAuthorizedKey`: exactly one
    key (no embedded newlines), a known ``<type>`` token, and a base64 blob
    whose embedded type string matches that token. Raises a typed
    ``Error('bad_request', ...)`` on any failure.
    """
    if not isinstance(key, str):
        raise Error("bad_request", "SSH public key must be a string")
    key = key.strip()
    if not key:
        raise Error("bad_request", "SSH public key is required")
    if "\n" in key or "\r" in key:
        raise Error(
            "bad_request",
            "Only a single SSH public key is allowed",
            description_code="bastion_ssh_key_invalid",
        )
    parts = key.split()
    if len(parts) < 2 or parts[0] not in _SSH_KEY_TYPES:
        raise Error(
            "bad_request",
            "Invalid SSH public key format",
            description_code="bastion_ssh_key_invalid",
        )
    try:
        blob = base64.b64decode(parts[1], validate=True)
        length = struct.unpack(">I", blob[:4])[0]
        embedded_type = blob[4 : 4 + length].decode("ascii")
    except Exception:
        raise Error(
            "bad_request",
            "Invalid SSH public key format",
            description_code="bastion_ssh_key_invalid",
        )
    if embedded_type != parts[0]:
        raise Error(
            "bad_request",
            "Invalid SSH public key format",
            description_code="bastion_ssh_key_invalid",
        )
    return key


class UsersService:
    """
    Users service for managing user-related operations.
    """

    @staticmethod
    def create(
        provider: str,
        category_id: str,
        uid: str,
        username: str,
        name: str,
        role_id: str,
        group_id: str,
        password: str = False,
        encrypted_password: str = False,
        photo: str = None,
        email: str = None,
        secondary_groups: list[str] = [],
    ) -> str:
        """
        Create a new user with the provided details.
        """
        if not RethinkRole.exists(role_id):
            raise Error(
                "not_found",
                f"Role with ID '{role_id}' does not exist.",
            )
        if not RethinkCategory.exists(category_id):
            raise Error(
                "not_found",
                f"Category with ID '{category_id}' does not exist.",
            )
        if not RethinkGroup.exists(group_id):
            raise Error(
                "not_found",
                f"Group with ID '{group_id}' does not exist.",
            )
        group = RethinkGroup(group_id)
        if password == False:
            password = Helpers.gen_random_password()
        else:
            bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        if encrypted_password != False:
            password = encrypted_password

        # If the user is created by SAML or LDAP and its configured to save the email we consider the email verified
        email_verified = False
        if provider in ["saml", "ldap"]:
            env_var = f"AUTHENTICATION_AUTHENTICATION_{provider.upper()}_SAVE_EMAIL"
            if os.environ.get(env_var, "").lower() == "true":
                email_verified = int(time.time())

        user = {
            "name": name,
            "uid": uid,
            "provider": provider,
            "active": True,
            "accessed": int(time.time()),
            "username": username,
            "password": password,
            "role": role_id,
            "category": category_id,
            "group": group_id,
            "email": email,
            "photo": photo,
            "default_templates": [],
            "quota": group.quota,
            "secondary_groups": secondary_groups,
            "password_history": [password],
            "email_verification_token": None,
            "email_verified": email_verified,
            "api_key": None,
        }

        user = RethinkUser.init_document(**user)
        UserStorage.isard_user_storage_add_user(user)

        from api.routes.users import clear_users_list_cache

        clear_users_list_cache()
        return user

    @staticmethod
    def check_user_exists(uid: str, category_id: str, provider: str) -> bool:
        """
        Check if a user exists based on uid, category_id, and provider.
        """
        return CommonUser.check_user_exists(
            uid=uid, category_id=category_id, provider=provider
        )

    @staticmethod
    def get_user_password_policy(
        category_id: str = None,
        role_id: str = None,
        provider: str = None,
        user_id: str = None,
    ) -> dict:
        """
        Get the password policy for a user based on category_id, role_id, provider or user_id.
        """
        print(
            f"Getting password policy for category_id: {category_id}, role_id: {role_id}, provider: {provider}, user_id: {user_id}"
        )
        return CommonUserPolicies.get_user_policy(
            subtype="password",
            category_id=category_id,
            role_id=role_id,
            provider=provider,
            user_id=user_id,
        )

    @staticmethod
    def get_user_vpn(user_id: str) -> dict:
        return IsardVpn.vpn_data("users", "config", False, user_id)

    @staticmethod
    def reset_user_vpn(user_id: str) -> None:
        return CommonUser.reset_vpn(user_id)

    @staticmethod
    def get_allowed_hardware(user_id: str, domain_id: str | None = None) -> dict:
        """
        Get the allowed hardware for a user, optionally considering an
        existing domain's current resource usage (so a desktop edit flow can
        show what the user could grow it to).
        """
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        payload = Helpers.gen_payload_from_user(user_id)
        return Quotas.get_hardware_allowed(payload, domain_id=domain_id)

    @staticmethod
    def get_user_info(user_id: str) -> dict:
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )

        return CommonUser.get_user_info(user_id)

    @staticmethod
    def get_user_config(payload: dict) -> dict:
        return CommonUser.user_config(payload)

    @staticmethod
    def set_user_email(user_id: str, email: str) -> None:
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        CommonUser.update_user(
            user_id, {"email": email}, revoke=False, force_email_verification=True
        )

    @staticmethod
    def get_user_bastion_ssh_key(user_id: str) -> dict:
        """Return the user's single bastion SSH public key (or None)."""
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        key = RethinkUser(user_id).bastion_ssh_key
        if not isinstance(key, str) or not key.strip():
            key = None
        return {"ssh_key": key}

    @staticmethod
    def set_user_bastion_ssh_key(user_id: str, ssh_key: str) -> None:
        """Set/replace the user's single bastion SSH public key."""
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        ssh_key = validate_ssh_public_key(ssh_key)
        CommonUser.update_user(user_id, {"bastion_ssh_key": ssh_key}, revoke=False)

    @staticmethod
    def delete_user_bastion_ssh_key(user_id: str) -> None:
        """Remove the user's bastion SSH public key."""
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        CommonUser.update_user(user_id, {"bastion_ssh_key": None}, revoke=False)

    @staticmethod
    def set_user_language(user_id: str, lang: str) -> None:
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        CommonUser.change_user_language(user_id, lang)

    @staticmethod
    def get_user_api_key(user_id: str) -> dict:
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        return CommonUser.get_api_key(user_id)

    @staticmethod
    def delete_user_api_key(user_id: str) -> None:
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        CommonUser.delete_api_key(user_id)

    @staticmethod
    def set_user_password(
        user_id: str, current_password: str, new_password: str
    ) -> None:
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )

        CommonUser.verify_password(user_id=user_id, password=current_password)
        CommonUser.change_password(password=new_password, user_id=user_id)

    @staticmethod
    def get_user_details(user_id: str) -> dict:
        return CommonUser.get_user(user_id, get_quota=False)

    @staticmethod
    def get_user_quotas(user_id: str) -> dict:
        return {
            **Quotas.get_applied_quota(user_id),
            **Quotas.Get(user_id, started_info=True),
        }

    @staticmethod
    def delete_user(user_id: str) -> None:
        """
        Delete the current user (self-deletion).
        """
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        CommonUser.delete_user(user_id, user_id, True)

        from api.routes.users import clear_users_list_cache

        clear_users_list_cache()

    @staticmethod
    def get_user_desktops(user_id: str) -> list:
        """
        Get all desktops for a user.
        """
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        return CommonDesktops.get_user_desktops(user_id)

    @staticmethod
    def get_user_desktop(desktop_id: str, user_id: str) -> dict:
        """
        Get a specific desktop for a user.
        """
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        return CommonDesktops.get_desktop(desktop_id)

    @staticmethod
    def get_user_vpn_data(kind: str, os: str | bool, user_id: str) -> dict:
        """
        Get VPN configuration data for a user.
        """
        return IsardVpn.vpn_data("users", kind, os, user_id)

    @staticmethod
    def get_webapp_desktops(user_id: str) -> list:
        """
        Get webapp desktops for a user.
        """
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        desktops = DomainsProcessed.list_webapp_desktops_for_user(user_id)
        return [
            d
            for d in desktops
            if not d.get("tag") or d.get("tag") and d.get("tag_visible")
        ]

    @staticmethod
    def get_webapp_templates(user_id: str) -> list:
        """
        Get webapp templates for a user.
        """
        return DomainsProcessed.list_webapp_templates_for_user(user_id)

    @staticmethod
    def groups_users_count(groups: list, user_id: str) -> int:
        """
        Count users in the specified groups.
        """
        return CommonGroups.groups_users_count(groups, user_id)

    @staticmethod
    def get_hardware_kind_allowed(user_id: str, kind: str) -> dict:
        """
        Get allowed hardware for a specific kind.
        """
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )
        payload = Helpers.gen_payload_from_user(user_id)
        return Quotas.get_hardware_kind_allowed(payload, kind)

    @staticmethod
    def get_applied_quota(user_id: str) -> dict:
        """
        Get the applied quota for a user.
        """
        return Quotas.get_applied_quota(user_id)

    @staticmethod
    def get_bastion_allowed(payload: dict) -> bool:
        """
        Check if the user can use bastion.
        """
        return Helpers.can_use_bastion(payload)
