#
#   Copyright © 2025 IsardVDI
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

from api.services.error import Error
from isardvdi_common.helpers.url_validation import validate_url_not_internal
from isardvdi_common.helpers.user_storage import UserStorage


def _ensure_external_url(url: str) -> None:
    """Reject provider URLs that resolve to an internal address: UserStorage
    opens a WebDAV connection to the configured host, so an unvalidated URL
    lets an admin reach internal/loopback services."""
    try:
        validate_url_not_internal(url)
    except Exception:
        raise Error(
            "bad_request",
            "URL points to a loopback/link-local/private/multicast address.",
            description_code="bad_request",
        )


class AdminUserStorageService:

    @staticmethod
    def auto_register(
        domain: str,
        user: str,
        password: str,
        intra_docker: bool,
        verify_cert: bool,
    ) -> str:
        # Skip the check in intra-docker mode: reaching a private address
        # is the operator's explicit intent there.
        if not intra_docker:
            scheme = "https" if verify_cert else "http"
            _ensure_external_url(f"{scheme}://{domain}")
        return UserStorage.isard_user_storage_provider_auto_register_auth(
            domain, user, password, intra_docker, verify_cert
        )

    @staticmethod
    def conn_test(
        provider: str,
        url: str,
        urlprefix: str,
        user: str,
        password: str,
        verify_cert: bool,
    ) -> None:
        _ensure_external_url(url)
        UserStorage.isard_user_storage_provider_basic_auth_test(
            provider, url, urlprefix, user, password, verify_cert
        )

    @staticmethod
    def get_login_auth(provider_id: str) -> str:
        return UserStorage.isard_user_storage_provider_login_auth(provider_id)

    @staticmethod
    def list_providers() -> list:
        return UserStorage.isard_user_storage_get_providers_ws()

    @staticmethod
    def get_provider(provider_id: str) -> dict:
        return UserStorage.isard_user_storage_get_provider(provider_id)

    @staticmethod
    def delete_provider(provider_id: str) -> None:
        UserStorage.isard_user_storage_provider_delete(provider_id)

    @staticmethod
    def reset_provider(provider_id: str) -> None:
        UserStorage.isard_user_storage_provider_reset(provider_id)

    @staticmethod
    def reset_all() -> None:
        UserStorage.isard_user_storage_reset_all()

    @staticmethod
    def add_provider_basic_auth(
        provider: str,
        name: str,
        description: str,
        url: str,
        urlprefix: str,
        access: str,
        quota: object,
        verify_cert: bool,
    ) -> str:
        # Validate at persistence time too: a stored internal URL would
        # otherwise be dialled on every later sync.
        _ensure_external_url(url)
        return UserStorage.isard_user_storage_provider_basic_auth_add(
            provider, name, description, url, urlprefix, access, quota, verify_cert
        )

    @staticmethod
    def sync(provider_id: str, item: str) -> None:
        if item in ["groups", "all"]:
            UserStorage.isard_user_storage_sync_groups(provider_id)
        if item in ["users", "all"]:
            UserStorage.isard_user_storage_sync_users(provider_id)

    @staticmethod
    def get_users() -> list:
        return UserStorage.isard_user_storage_get_users()
