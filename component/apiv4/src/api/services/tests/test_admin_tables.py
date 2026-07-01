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


class TestDesktopsPriorityShutdownBounds:
    """Bound shutdown values: max in (0, 525600], interval time in [-525600, -1]."""

    def _rule(self, max_time, interval_time=-10):
        return {
            "id": "p1",
            "name": "p1",
            "shutdown": {
                "max": max_time,
                "notify_intervals": [{"time": interval_time, "type": "danger"}],
            },
        }

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_in_range_insert_passes(self, _check, mock_insert):
        AdminTablesService.insert_table_item("desktops_priority", self._rule(525600))
        assert mock_insert.called

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_max_over_one_year_rejected(self, _check, mock_insert):
        import pytest
        from api.services.error import Error

        with pytest.raises(Error) as exc_info:
            AdminTablesService.insert_table_item(
                "desktops_priority", self._rule(525601)
            )
        assert exc_info.value.args[0] == "bad_request"
        assert not mock_insert.called

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_non_positive_max_rejected(self, _check, mock_insert):
        import pytest
        from api.services.error import Error

        with pytest.raises(Error) as exc_info:
            AdminTablesService.insert_table_item("desktops_priority", self._rule(0))
        assert exc_info.value.args[0] == "bad_request"
        assert not mock_insert.called

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_interval_time_too_far_back_rejected(self, _check, mock_insert):
        import pytest
        from api.services.error import Error

        with pytest.raises(Error) as exc_info:
            AdminTablesService.insert_table_item(
                "desktops_priority", self._rule(210, interval_time=-525601)
            )
        assert exc_info.value.args[0] == "bad_request"
        assert not mock_insert.called

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_non_negative_interval_time_rejected(self, _check, mock_insert):
        import pytest
        from api.services.error import Error

        with pytest.raises(Error) as exc_info:
            AdminTablesService.insert_table_item(
                "desktops_priority", self._rule(210, interval_time=0)
            )
        assert exc_info.value.args[0] == "bad_request"
        assert not mock_insert.called

    @patch("api.services.admin.tables.ApiAdmin.update_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_update_out_of_range_rejected(self, _check, mock_update):
        import pytest
        from api.services.error import Error

        with pytest.raises(Error) as exc_info:
            AdminTablesService.update_table_item(
                "desktops_priority", self._rule(525601)
            )
        assert exc_info.value.args[0] == "bad_request"
        assert not mock_update.called

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_other_table_with_shutdown_key_untouched(self, _check, mock_insert):
        # The guard is keyed on table name — an unrelated table carrying a
        # ``shutdown`` field must not be validated against these bounds.
        AdminTablesService.insert_table_item(
            "interfaces", {"id": "i1", "name": "i1", "shutdown": {"max": 999999}}
        )
        assert mock_insert.called


class TestInterfaceLabOptsValidation:
    """Per-interface lab_opts gate: an enabled lab option is allowed only on
    kind=ovs/personal outside VLAN 4095 (wireguard infra). apiv3 enforced this
    via a Cerberus ``check_with``; the apiv4 raw-dict path re-asserts it on
    INSERT and UPDATE. An all-false (or absent) lab_opts is always accepted."""

    LAB_FLAGS = (
        "mac_spoofing",
        "stp_bpdu",
        "broadcast_unlimited",
        "multicast_unlimited",
    )

    def _iface(self, **over):
        base = {"id": "if1", "name": "if1", "kind": "ovs", "net": "1002"}
        base.update(over)
        return base

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_each_flag_accepted_on_ovs_outside_4095(self, _dup, mock_insert):
        for flag in self.LAB_FLAGS:
            AdminTablesService.insert_table_item(
                "interfaces", self._iface(lab_opts={flag: True})
            )
        assert mock_insert.call_count == len(self.LAB_FLAGS)

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_lab_opts_normalized_to_all_four_bools(self, _dup, mock_insert):
        data = self._iface(lab_opts={"mac_spoofing": True})
        AdminTablesService.insert_table_item("interfaces", data)
        stored = mock_insert.call_args[0][1]
        assert stored["lab_opts"] == {
            "mac_spoofing": True,
            "stp_bpdu": False,
            "broadcast_unlimited": False,
            "multicast_unlimited": False,
        }

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_flag_rejected_on_non_ovs_kind(self, _dup, mock_insert):
        import pytest
        from api.services.error import Error

        for kind in ("bridge", "network"):
            with pytest.raises(Error) as exc:
                AdminTablesService.insert_table_item(
                    "interfaces",
                    self._iface(kind=kind, net="x", lab_opts={"mac_spoofing": True}),
                )
            assert exc.value.args[0] == "bad_request"
        assert not mock_insert.called

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_flag_rejected_on_ovs_vlan_4095(self, _dup, mock_insert):
        import pytest
        from api.services.error import Error

        with pytest.raises(Error):
            AdminTablesService.insert_table_item(
                "interfaces", self._iface(net="4095", lab_opts={"stp_bpdu": True})
            )
        assert not mock_insert.called

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_flag_rejected_on_personal_range_covering_4095(self, _dup, mock_insert):
        import pytest
        from api.services.error import Error

        for net in ("4000-4100", "1-4095", "4095-4095", "4095-4100"):
            with pytest.raises(Error):
                AdminTablesService.insert_table_item(
                    "interfaces",
                    self._iface(
                        kind="personal", net=net, lab_opts={"mac_spoofing": True}
                    ),
                )
        assert not mock_insert.called

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_personal_range_below_4095_accepted(self, _dup, mock_insert):
        AdminTablesService.insert_table_item(
            "interfaces",
            self._iface(kind="personal", net="4000-4094", lab_opts={"stp_bpdu": True}),
        )
        assert mock_insert.called

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_all_false_accepted_even_on_4095(self, _dup, mock_insert):
        AdminTablesService.insert_table_item(
            "interfaces",
            self._iface(net="4095", lab_opts={f: False for f in self.LAB_FLAGS}),
        )
        assert mock_insert.called

    @patch("api.services.admin.tables.ApiAdmin.insert_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_absent_lab_opts_accepted(self, _dup, mock_insert):
        AdminTablesService.insert_table_item("interfaces", self._iface(net="4095"))
        assert mock_insert.called

    @patch("api.services.admin.tables.ApiAdmin.update_table_item")
    @patch("api.services.admin.tables.ApiAdmin.admin_table_list")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_partial_update_merges_stored_kind_net_and_rejects_4095(
        self, _dup, mock_list, mock_update
    ):
        import pytest
        from api.services.error import Error

        # Partial edit enabling a flag; kind/net live only on the stored row
        # (mirrors apiv3 re-validating {**old_row, **data}).
        mock_list.return_value = {
            "id": "if1",
            "name": "if1",
            "kind": "ovs",
            "net": "4095",
        }
        with pytest.raises(Error):
            AdminTablesService.update_table_item(
                "interfaces",
                {"id": "if1", "name": "if1", "lab_opts": {"mac_spoofing": True}},
            )
        assert not mock_update.called

    @patch("api.services.admin.tables.ApiAdmin.update_table_item")
    @patch("api.services.admin.tables.Helpers.check_duplicate")
    def test_full_doc_update_accepted_on_ovs(self, _dup, mock_update):
        AdminTablesService.update_table_item(
            "interfaces", self._iface(lab_opts={"mac_spoofing": True})
        )
        assert mock_update.called
