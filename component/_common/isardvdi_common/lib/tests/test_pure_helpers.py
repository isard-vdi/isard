# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the pure-logic helpers scattered across isardvdi_common/lib/.

Most of `lib/` is thin wrappers over RethinkDB queries that need MockThink
to test meaningfully; the handful of genuinely pure functions below are
what this file targets — high-leverage per test because they're shared
by apiv4 + engine + change-handler and run on every request / event.
"""

import portion as P
import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.isard_viewer import default_guest_properties
from isardvdi_common.lib.bookings.reservables_planner_compute import (
    _sorted_atomic_items,
)
from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed
from isardvdi_common.lib.domains.disk_resolver import resolve_parent_disk
from isardvdi_common.lib.notifications.notifications_templates import sanitize_href
from isardvdi_common.lib.storage.storage import StorageProcessed
from isardvdi_common.schemas.domains import DesktopStatusEnum

# -------------------------------------------------------------------------
# sanitize_href — security-relevant scheme allow-list
# -------------------------------------------------------------------------


class TestSanitizeHref:
    @pytest.mark.parametrize(
        "href", ["http://isard.example", "https://a.b/c", "/relative/path", "#anchor"]
    )
    def test_safe_schemes_passthrough(self, href):
        assert sanitize_href(href) == href

    @pytest.mark.parametrize(
        "href",
        [
            "javascript:alert(1)",
            "JavaScript:alert(1)",  # case-insensitive guard
            "  javascript:alert(1)  ",  # leading/trailing whitespace
            "data:text/html,<script>",
            "vbscript:msgbox(1)",
            "VBSCRIPT:msgbox(1)",
        ],
    )
    def test_dangerous_schemes_blocked(self, href):
        assert sanitize_href(href) is None

    def test_empty_and_none_pass_through(self):
        assert sanitize_href("") == ""
        assert sanitize_href(None) is None

    def test_colon_without_recognized_scheme_is_allowed(self):
        # e.g. a path containing a colon inside a query string
        assert sanitize_href("/path?a=1:2") == "/path?a=1:2"

    def test_mailto_allowed(self):
        # mailto: is not in the deny-list, so it passes through.
        # Pinning this so a future tightening of the allow-list has to
        # update the test.
        assert sanitize_href("mailto:admin@isard") == "mailto:admin@isard"


# -------------------------------------------------------------------------
# StorageProcessed.parse_disks — data reshaping
# -------------------------------------------------------------------------


class TestParseDisks:
    def test_empty_list_returns_empty(self):
        assert StorageProcessed.parse_disks([]) == []

    def test_unpacks_qemu_img_info_into_top_level(self):
        disks = [
            {
                "id": "s1",
                "qemu-img-info": {"actual-size": 1024, "virtual-size": 8192},
            }
        ]
        out = StorageProcessed.parse_disks(disks)
        assert out[0]["actual_size"] == 1024
        assert out[0]["virtual_size"] == 8192
        assert "qemu-img-info" not in out[0]

    def test_collapses_status_logs_to_last_timestamp(self):
        disks = [
            {
                "id": "s1",
                "status_logs": [
                    {"time": 100, "status": "created"},
                    {"time": 200, "status": "ready"},
                    {"time": 300, "status": "deleted"},
                ],
            }
        ]
        out = StorageProcessed.parse_disks(disks)
        assert out[0]["last"] == 300
        assert "status_logs" not in out[0]

    def test_disk_without_optional_fields_passes_through_untouched(self):
        disks = [{"id": "s1", "status": "ready"}]
        out = StorageProcessed.parse_disks(disks)
        assert out == [{"id": "s1", "status": "ready"}]

    def test_multiple_disks_each_transformed_independently(self):
        disks = [
            {"id": "s1", "qemu-img-info": {"actual-size": 1, "virtual-size": 2}},
            {"id": "s2", "status_logs": [{"time": 500}]},
            {"id": "s3"},
        ]
        out = StorageProcessed.parse_disks(disks)
        assert out[0]["actual_size"] == 1
        assert out[1]["last"] == 500
        assert out[2] == {"id": "s3"}


# -------------------------------------------------------------------------
# _sorted_atomic_items — flattens compound IntervalDict keys
# -------------------------------------------------------------------------
# This function was introduced as an unimplemented recursion stub in the
# initial isardvdi_common refactor commit. Every caller in the file
# (intersect_same_subitem_plan, intersect_different_subitem_plan, ...)
# would have raised RecursionError at runtime. Fixed alongside these
# tests to perform the documented "extract + sort atomic intervals"
# operation.


class TestSortedAtomicItems:
    def test_empty_interval_dict_returns_empty(self):
        assert _sorted_atomic_items(P.IntervalDict()) == []

    def test_single_atomic_interval(self):
        d = P.IntervalDict({P.closed(1, 3): {"units": 1, "id": "a"}})
        items = _sorted_atomic_items(d)
        assert len(items) == 1
        assert items[0][0].lower == 1
        assert items[0][0].upper == 3
        assert items[0][1] == {"units": 1, "id": "a"}

    def test_compound_key_is_split_into_atomic_parts(self):
        """A compound interval like `closed(1,3) | closed(5,7)` is one
        IntervalDict key but two atomic intervals. The helper flattens
        them into two items that share the same value dict.
        """
        d = P.IntervalDict(
            {P.closed(1, 3) | P.closed(5, 7): {"units": 2, "id": "compound"}}
        )
        items = _sorted_atomic_items(d)
        assert len(items) == 2
        bounds = [(it[0].lower, it[0].upper) for it in items]
        assert (1, 3) in bounds
        assert (5, 7) in bounds
        # Both share the same value dict (same reference — the helper
        # does NOT deep-copy).
        assert items[0][1] == items[1][1] == {"units": 2, "id": "compound"}

    def test_multiple_keys_sorted_by_lower_bound(self):
        d = P.IntervalDict(
            {
                P.closed(10, 12): {"id": "c", "units": 3},
                P.closed(1, 2): {"id": "a", "units": 1},
                P.closed(5, 7): {"id": "b", "units": 2},
            }
        )
        items = _sorted_atomic_items(d)
        assert [pair[1]["id"] for pair in items] == ["a", "b", "c"]

    def test_result_tuple_shape_matches_caller_expectations(self):
        """`ReservablesPlannerCompute.intersect_same_subitem_plan` reads
        `item[0].lower`, `item[0].upper`, `item[1]["units"]`,
        `item[1]["id"]`. Pin that wire shape so a future refactor that
        changes the tuple order breaks this test alongside the callers.
        """
        d = P.IntervalDict({P.closed(1, 3): {"units": 5, "id": "xyz"}})
        (interval, value) = _sorted_atomic_items(d)[0]
        assert hasattr(interval, "lower") and hasattr(interval, "upper")
        assert interval.lower == 1 and interval.upper == 3
        assert value["units"] == 5
        assert value["id"] == "xyz"


# -------------------------------------------------------------------------
# default_guest_properties — default viewer credentials / options shape
# -------------------------------------------------------------------------


class TestDefaultGuestProperties:
    def test_returns_fresh_dict_each_call(self):
        """A caller that mutates the return value must not affect future
        callers — the helper returns a new dict, not a shared module-level
        constant."""
        a = default_guest_properties()
        a["credentials"]["password"] = "mutated"
        b = default_guest_properties()
        assert b["credentials"]["password"] == "pirineus"

    def test_has_every_viewer_kind_with_null_options(self):
        gp = default_guest_properties()
        # Pin the viewer-kind set — the frontend router / SDK reads each
        # of these keys to decide which viewer button to render.
        assert set(gp["viewers"].keys()) == {
            "file_spice",
            "browser_vnc",
            "file_rdpgw",
            "file_rdpvpn",
            "browser_rdp",
        }
        for v in gp["viewers"].values():
            assert v == {"options": None}

    def test_fullscreen_default_is_false(self):
        assert default_guest_properties()["fullscreen"] is False


# -------------------------------------------------------------------------
# DesktopsProcessed.parse_frontend_desktop_status — status rewriting
# -------------------------------------------------------------------------
#
# Rewrites the raw engine-level status into the one the frontend cards
# should display. Three rewrites:
#   1. Any `Creating*` (except `CreatingAndStarting`) collapses to
#      `Creating` — the frontend only shows one spinner.
#   2. `Started` without a viewer passwd is effectively still starting.
#   3. `Started` with a wireguard interface but no guest_ip is
#      "waiting for IP" — the direct-viewer can't open yet.


class TestParseFrontendDesktopStatus:
    def _desktop(self, status, **overrides):
        base = {
            "id": "d1",
            "status": status,
            "viewer": {"passwd": "x", "guest_ip": "10.0.0.1"},
            "create_dict": {"hardware": {"interfaces": []}},
        }
        base.update(overrides)
        return base

    def test_creating_disk_collapses_to_creating(self):
        d = self._desktop("CreatingDisk")
        out = DesktopsProcessed.parse_frontend_desktop_status(d)
        assert out["status"] == DesktopStatusEnum.creating.value

    @pytest.mark.parametrize(
        "raw",
        ["CreatingTemplate", "CreatingFromScratch", "CreatingDiskFromScratch"],
    )
    def test_any_creating_prefix_collapses_except_creating_and_starting(self, raw):
        d = self._desktop(raw)
        out = DesktopsProcessed.parse_frontend_desktop_status(d)
        assert out["status"] == DesktopStatusEnum.creating.value

    def test_creating_and_starting_is_preserved(self):
        d = self._desktop(DesktopStatusEnum.creating_and_starting.value)
        out = DesktopsProcessed.parse_frontend_desktop_status(d)
        assert out["status"] == DesktopStatusEnum.creating_and_starting.value

    def test_started_without_passwd_becomes_starting(self):
        d = self._desktop(DesktopStatusEnum.started.value, viewer={})
        out = DesktopsProcessed.parse_frontend_desktop_status(d)
        assert out["status"] == DesktopStatusEnum.starting.value

    def test_started_with_passwd_stays_started_when_no_wireguard(self):
        d = self._desktop(DesktopStatusEnum.started.value)
        out = DesktopsProcessed.parse_frontend_desktop_status(d)
        assert out["status"] == DesktopStatusEnum.started.value

    def test_started_wireguard_without_ip_becomes_waiting_ip(self):
        d = self._desktop(
            DesktopStatusEnum.started.value,
            viewer={"passwd": "x"},  # no guest_ip
            create_dict={"hardware": {"interfaces": [{"id": "wireguard"}]}},
        )
        out = DesktopsProcessed.parse_frontend_desktop_status(d)
        assert out["status"] == DesktopStatusEnum.waiting_ip.value

    def test_started_wireguard_with_ip_stays_started(self):
        d = self._desktop(
            DesktopStatusEnum.started.value,
            create_dict={"hardware": {"interfaces": [{"id": "wireguard"}]}},
        )
        out = DesktopsProcessed.parse_frontend_desktop_status(d)
        assert out["status"] == DesktopStatusEnum.started.value

    def test_non_started_non_creating_passes_through_untouched(self):
        for status in [
            DesktopStatusEnum.stopped.value,
            DesktopStatusEnum.failed.value,
            DesktopStatusEnum.downloading.value,
            DesktopStatusEnum.suspended.value,
        ]:
            d = self._desktop(status)
            out = DesktopsProcessed.parse_frontend_desktop_status(d)
            assert out["status"] == status


# -------------------------------------------------------------------------
# DesktopsProcessed.parse_domain_update — status-flip guard
# -------------------------------------------------------------------------
#
# Regression: prior to the fix, parse_domain_update unconditionally set
# status=Updating on every call, even for desktops currently running
# (Started/Paused/...). The engine handler in DomainsChangesThread only
# catches Stopped|Failed|Downloaded → Updating, so a Started desktop
# edit would leave the row stuck in Updating with libvirt still running
# the domain. Guard the flip so running-side states stay put.


class TestParseDomainUpdateStatusGuard:
    def _patch_caches(self, monkeypatch, status):
        monkeypatch.setattr(
            "isardvdi_common.lib.domains.desktops.desktops.Caches.get_document",
            lambda table, domain_id: {
                "id": domain_id,
                "status": status,
                "name": "old-name",
                "description": "old",
                "hardware": {},
                "create_dict": {"hardware": {"interfaces": [], "disks": []}},
                "forced_hyp": None,
                "favourite_hyp": None,
                "server": False,
                "server_autostart": False,
                "xml": "<domain/>",
                "guest_properties": {},
            },
        )

    @pytest.mark.parametrize(
        "running_status",
        [
            DesktopStatusEnum.started.value,
            DesktopStatusEnum.paused.value,
            DesktopStatusEnum.starting.value,
            DesktopStatusEnum.stopping.value,
            DesktopStatusEnum.shutting_down.value,
            DesktopStatusEnum.waiting_ip.value,
        ],
    )
    def test_running_states_are_not_flipped_to_updating(
        self, monkeypatch, running_status
    ):
        self._patch_caches(monkeypatch, running_status)
        out = DesktopsProcessed.parse_domain_update(
            "d-running", {"description": "edited"}
        )
        assert "status" not in out
        assert out.get("description") == "edited"

    @pytest.mark.parametrize(
        "idle_status",
        [
            DesktopStatusEnum.stopped.value,
            DesktopStatusEnum.failed.value,
            # "Downloaded" is a string literal used by the engine; not
            # exposed in DesktopStatusEnum.
            "Downloaded",
        ],
    )
    def test_idle_states_flip_to_updating_so_engine_regenerates_xml(
        self, monkeypatch, idle_status
    ):
        self._patch_caches(monkeypatch, idle_status)
        out = DesktopsProcessed.parse_domain_update("d-idle", {"description": "edited"})
        assert out.get("status") == DesktopStatusEnum.updating.value


# -------------------------------------------------------------------------
# resolve_parent_disk — unified handling of v3/downloaded/legacy domain shapes
# -------------------------------------------------------------------------


class TestResolveParentDisk:
    """Pin the three shapes that produce a parent disk path on this branch.

    Before 42a235720 the engine wrote the on-disk file to
    ``domain.hardware.disks[0].file``; after 42a235720 downloaded
    domains only carry ``create_dict.hardware.disks[0].storage_id`` and
    the path is resolved via the Storage model. Templates and derived
    desktops must handle both, plus the rare legacy ``file`` key under
    ``create_dict``.
    """

    def test_storage_id_path_resolves_via_storage_model(self, monkeypatch):
        monkeypatch.setattr(
            "isardvdi_common.models.storage.Storage",
            lambda storage_id: type("_S", (), {"path": f"/data/{storage_id}.qcow2"})(),
        )
        domain = {
            "id": "d-1",
            "create_dict": {
                "hardware": {"disks": [{"storage_id": "s-abc"}]},
            },
        }
        assert resolve_parent_disk(domain) == "/data/s-abc.qcow2"

    def test_create_dict_file_key_wins_when_storage_id_absent(self):
        domain = {
            "id": "d-2",
            "create_dict": {
                "hardware": {"disks": [{"file": "/legacy/v3-path.qcow2"}]},
            },
        }
        assert resolve_parent_disk(domain) == "/legacy/v3-path.qcow2"

    def test_top_level_hardware_file_is_last_resort(self):
        """Pre-42a235720 shape that may still exist on long-lived DBs."""
        domain = {
            "id": "d-3",
            "hardware": {"disks": [{"file": "/old/shape.qcow2"}]},
        }
        assert resolve_parent_disk(domain) == "/old/shape.qcow2"

    def test_create_dict_takes_precedence_over_top_level_hardware(self, monkeypatch):
        monkeypatch.setattr(
            "isardvdi_common.models.storage.Storage",
            lambda storage_id: type("_S", (), {"path": f"/new/{storage_id}"})(),
        )
        domain = {
            "id": "d-4",
            "create_dict": {
                "hardware": {"disks": [{"storage_id": "s-new"}]},
            },
            "hardware": {"disks": [{"file": "/stale/old.qcow2"}]},
        }
        # The post-42a235720 location is authoritative; the legacy key
        # must not silently win.
        assert resolve_parent_disk(domain) == "/new/s-new"

    def test_no_resolvable_disk_raises(self):
        with pytest.raises(Error) as ei:
            resolve_parent_disk({"id": "d-5", "create_dict": {"hardware": {}}})
        assert ei.value.error["description_code"] == "domain_no_parent_disk"

    def test_empty_disk_list_raises(self):
        with pytest.raises(Error) as ei:
            resolve_parent_disk(
                {
                    "id": "d-6",
                    "create_dict": {"hardware": {"disks": []}},
                    "hardware": {"disks": []},
                }
            )
        assert ei.value.error["description_code"] == "domain_no_parent_disk"
