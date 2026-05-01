# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for AdminTablesService.insert_table_item — covers the
``default_setter`` matrix ported from the apiv3 Cerberus schemas
(``api_admin_table_defaults.apply_table_defaults``). Every webapp
``Add`` modal (desktops_priority, bookings_priority, interfaces,
qos_*, remotevpn, videos) submits form data without an ``id``; the
service must auto-fill defaults before delegating to the rdb writer
so the modal lands without a 400."""

import re
from unittest.mock import patch

from api.services.admin.tables import AdminTablesService

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class TestInsertTableItemDefaults:
    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_genuuid_fills_missing_id(self, _check_dup, mock_insert):
        AdminTablesService.insert_table_item("desktops_priority", {"name": "p1"})
        forwarded = mock_insert.call_args.args[1]
        assert UUID_RE.match(forwarded["id"]), forwarded["id"]

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_existing_id_is_preserved(self, _check_dup, mock_insert):
        AdminTablesService.insert_table_item(
            "desktops_priority", {"id": "fixed-id", "name": "p1"}
        )
        forwarded = mock_insert.call_args.args[1]
        assert forwarded["id"] == "fixed-id"

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_groups_get_uid_uuid(self, _check_dup, mock_insert):
        # ``groups`` had ``default_setter: genuuid`` on both ``id`` and ``uid``
        # in the apiv3 schema.
        AdminTablesService.insert_table_item("groups", {"name": "g1"})
        forwarded = mock_insert.call_args.args[1]
        assert UUID_RE.match(forwarded["id"])
        assert UUID_RE.match(forwarded["uid"])

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    def test_secrets_get_secret_default(self, mock_insert):
        AdminTablesService.insert_table_item(
            "secrets", {"id": "s-1", "category_id": "default"}
        )
        forwarded = mock_insert.call_args.args[1]
        # gensecret returns 32 random bytes b64-encoded → 44 chars incl. ``=``
        assert isinstance(forwarded["secret"], str)
        assert len(forwarded["secret"]) >= 40

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    def test_media_iso_gets_cd_icon(self, mock_insert):
        AdminTablesService.insert_table_item("media", {"name": "m1", "kind": "iso"})
        forwarded = mock_insert.call_args.args[1]
        assert forwarded["icon"] == "fa-circle-o"

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    def test_media_non_iso_gets_floppy_icon(self, mock_insert):
        AdminTablesService.insert_table_item("media", {"name": "m1", "kind": "img"})
        forwarded = mock_insert.call_args.args[1]
        assert forwarded["icon"] == "fa-floppy-o"

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    def test_hypervisors_storage_pools_default_list(self, mock_insert):
        AdminTablesService.insert_table_item("hypervisors", {"id": "hyper1"})
        forwarded = mock_insert.call_args.args[1]
        assert forwarded["storage_pools"] == ["00000000-0000-0000-0000-000000000000"]
        assert forwarded["virt_pools"] == ["00000000-0000-0000-0000-000000000000"]

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    def test_unregistered_table_gets_no_defaults(self, mock_insert):
        AdminTablesService.insert_table_item(
            "some_unregistered_table", {"name": "x", "id": "explicit"}
        )
        forwarded = mock_insert.call_args.args[1]
        assert forwarded == {"name": "x", "id": "explicit"}


class TestInsertTableItemEmptyBody:
    """Pins Bug 32 — empty body must 400, not 500.

    Tables whose default_setter matrix doesn't auto-generate an ``id``
    (``hypervisors``, ``hypervisors_pools``) used to crash deep inside
    ``ApiAdmin.insert_table_item`` on ``data["id"]`` KeyError. The
    route's generic ``except Exception`` re-wrapped that as 500
    "Failed to insert table item".

    The fix raises an explicit ``Error("bad_request", "Missing 'id'")``
    when ``id`` is missing AND ``apply_table_defaults`` didn't fill it
    in. The route's typed ``except Error: raise`` then surfaces it as
    400.
    """

    def test_hypervisors_empty_body_raises_bad_request(self):
        import pytest
        from api.services.error import Error

        with pytest.raises(Error) as exc_info:
            AdminTablesService.insert_table_item("hypervisors", {})
        assert exc_info.value.args[0] == "bad_request"
        assert "id" in exc_info.value.args[1].lower()

    def test_hypervisors_pools_empty_body_raises_bad_request(self):
        import pytest
        from api.services.error import Error

        with pytest.raises(Error) as exc_info:
            AdminTablesService.insert_table_item("hypervisors_pools", {})
        assert exc_info.value.args[0] == "bad_request"

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_hypervisors_with_id_passes_through(self, _check, mock_insert):
        """Sanity — the new id-required guard does not break the
        normal hypervisor create flow that the webapp form actually
        sends.
        """
        AdminTablesService.insert_table_item(
            "hypervisors",
            {
                "id": "hyper-new",
                "hostname": "host-1",
                "user": "root",
                "port": "22",
                "enabled": True,
            },
        )
        forwarded = mock_insert.call_args.args[1]
        assert forwarded["id"] == "hyper-new"

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_genuuid_table_still_works_without_id(self, _check, mock_insert):
        """Tables that DO auto-generate an id (e.g. ``categories``)
        keep working with an empty-id body — ``apply_table_defaults``
        fills it in before the new guard runs.
        """
        AdminTablesService.insert_table_item("categories", {"name": "cat-1"})
        forwarded = mock_insert.call_args.args[1]
        assert UUID_RE.match(forwarded["id"]), forwarded["id"]
