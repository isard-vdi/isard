#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``ReservablesProcessed`` (tier 3.4 batch 3 — migrated
from apiv4 ``services/reservables.py:update_item``).
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.bookings import reservables as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.ReservablesProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.ReservablesProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Processed": mod.ReservablesProcessed}


class TestGetItem:
    def test_returns_row_when_present(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = {
            "id": "g1",
            "name": "GPU 1",
        }
        result = stub_rdb["Processed"].get_item("gpus", "g1")
        assert result == {"id": "g1", "name": "GPU 1"}
        stub_rdb["mock_table"].assert_any_call("gpus")
        stub_rdb["mock_table"].return_value.get.assert_called_with("g1")

    def test_returns_none_when_missing(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = None
        assert stub_rdb["Processed"].get_item("gpus", "missing") is None


class TestNameExistsForOther:
    def test_true_when_match(self, stub_rdb):
        stub_rdb["mock_table"].return_value.filter.return_value.run.return_value = [
            {"id": "other"}
        ]
        assert stub_rdb["Processed"].name_exists_for_other("gpus", "n", "g1") is True
        stub_rdb["mock_table"].assert_any_call("gpus")

    def test_false_when_no_match(self, stub_rdb):
        stub_rdb["mock_table"].return_value.filter.return_value.run.return_value = []
        assert stub_rdb["Processed"].name_exists_for_other("gpus", "n", "g1") is False


class TestUpdateItem:
    def test_calls_update_when_data(self, stub_rdb):
        stub_rdb["Processed"].update_item("gpus", "g1", {"name": "renamed"})
        stub_rdb["mock_table"].return_value.get.assert_called_with("g1")
        stub_rdb["mock_table"].return_value.get.return_value.update.assert_called_with(
            {"name": "renamed"}
        )

    def test_noop_when_empty(self, stub_rdb):
        stub_rdb["Processed"].update_item("gpus", "g1", {})
        stub_rdb["mock_table"].return_value.get.return_value.update.assert_not_called()


class TestResourceItemsGpusAddItem:
    """Pins Bug 36 — ``ResourceItemsGpus.add_item`` must include
    ``reservable_type='gpus'`` in the row it builds before validating
    against ``GPUsModel``. Without it, the Pydantic Literal field
    rejected the dict and the route surfaced as 500 "Failed to add
    reservable item for gpus".
    """

    @pytest.fixture
    def gpu_stub(self, monkeypatch):
        from isardvdi_common.lib.bookings import reservables as mod

        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(
            mod.ResourceItemsGpus, "_rdb_context", classmethod(lambda cls: _Ctx())
        )
        monkeypatch.setattr(
            type(mod.ResourceItemsGpus),
            "_rdb_connection",
            property(lambda self: MagicMock(name="conn")),
        )
        mock_table = MagicMock(name="r.table")
        monkeypatch.setattr(mod.r, "table", mock_table)
        # gpu_profiles row
        gpu_profile = {
            "architecture": "Ampere",
            "brand": "NVIDIA",
            "memory": "48G",
            "model": "L40",
            "description": "default desc",
        }

        # First call returns the profile, subsequent calls return for the insert
        # We need to set up the chain for `r.table("gpu_profiles").get(id).run()`
        # AND `r.table("gpus").insert(new_gpu, conflict="update").run()`
        def table_router(name):
            t = MagicMock(name=f"table-{name}")
            if name == "gpu_profiles":
                t.get.return_value.run.return_value = gpu_profile
            elif name == "gpus":
                t.insert.return_value.run.return_value = {"inserted": 1}
            return t

        mock_table.side_effect = table_router
        # Helpers._check is a static method that returns whether a key is
        # present in the rdb result; just have it return the truthy flag.
        monkeypatch.setattr(
            mod.Helpers, "_check", staticmethod(lambda res, key: bool(res.get(key)))
        )
        return mod.ResourceItemsGpus

    def test_adds_reservable_type_gpus(self, gpu_stub):
        result = gpu_stub.add_item(
            {"name": "GPU-1", "bookable": "L40", "description": "test"}
        )
        # The smoking-gun assertion: the row passed to GPUsModel — and
        # written to the gpus table — MUST carry reservable_type="gpus".
        assert result["reservable_type"] == "gpus"
        # Sanity: the description from the request (non-empty) overrides
        # the gpu_profile default; brand/memory/model come from the
        # profile.
        assert result["description"] == "test"
        assert result["brand"] == "NVIDIA"
        assert result["memory"] == "48G"
        assert result["model"] == "L40"
        # profiles_enabled / physical_device default to neutral values.
        assert result["profiles_enabled"] == []
        assert result["physical_device"] is None


class TestDeassignDeploymentsWithGpu:
    """Bug 3 (audit) — when an admin disables a vGPU profile in use by
    a deployment, ``ResourceItemsGpus.deassign_deployments_with_gpu``
    must rewrite ``deployments.create_dict[*].reservables.vgpus`` so the
    disabled subitem no longer appears. The shape of ``create_dict``
    changed during the apiv4 port (now a list of dicts), so this test
    pins the contract to catch any regression.
    """

    @pytest.fixture
    def gpu_only_stub(self, monkeypatch):
        from isardvdi_common.lib.bookings import reservables as mod

        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(
            mod.ResourceItemsGpus, "_rdb_context", classmethod(lambda cls: _Ctx())
        )
        monkeypatch.setattr(
            type(mod.ResourceItemsGpus),
            "_rdb_connection",
            property(lambda self: MagicMock(name="conn")),
        )
        mock_table = MagicMock(name="r.table")
        monkeypatch.setattr(mod.r, "table", mock_table)
        # ``r.args(...)`` is a top-level rdb operator; MagicMock doesn't
        # intercept it, so we replace it with a sentinel for clean
        # assertions.
        monkeypatch.setattr(
            mod.r, "args", lambda x: ("ARGS", tuple(x) if hasattr(x, "__iter__") else x)
        )
        return {"mock_table": mock_table, "Cls": mod.ResourceItemsGpus, "mod": mod}

    def test_no_op_on_empty_deployments(self, gpu_only_stub):
        gpu_only_stub["Cls"].deassign_deployments_with_gpu("NVIDIA-A40-1Q", [])
        # No call to r.table for an empty list — the for-range never executes.
        gpu_only_stub["mock_table"].assert_not_called()

    def test_targets_deployments_table(self, gpu_only_stub):
        gpu_only_stub[
            "mock_table"
        ].return_value.get_all.return_value.update.return_value.run.return_value = {
            "replaced": 2
        }
        gpu_only_stub["Cls"].deassign_deployments_with_gpu(
            "NVIDIA-A40-1Q", ["dep-1", "dep-2"]
        )
        gpu_only_stub["mock_table"].assert_any_call("deployments")

    def test_passes_deployment_ids_to_get_all(self, gpu_only_stub):
        gpu_only_stub[
            "mock_table"
        ].return_value.get_all.return_value.update.return_value.run.return_value = {
            "replaced": 0
        }
        gpu_only_stub["Cls"].deassign_deployments_with_gpu(
            "NVIDIA-A40-1Q", ["dep-1", "dep-2", "dep-3"]
        )
        gpu_only_stub["mock_table"].return_value.get_all.assert_called_once_with(
            ("ARGS", ("dep-1", "dep-2", "dep-3"))
        )

    def test_batches_at_100_deployments(self, gpu_only_stub):
        """The function processes up to 100 deployments per rdb call.
        With 250 deployments we expect 3 batches.
        """
        gpu_only_stub[
            "mock_table"
        ].return_value.get_all.return_value.update.return_value.run.return_value = {
            "replaced": 0
        }
        deployments = [f"dep-{i}" for i in range(250)]
        gpu_only_stub["Cls"].deassign_deployments_with_gpu("NVIDIA-A40-1Q", deployments)
        # Three rdb calls total
        assert gpu_only_stub["mock_table"].return_value.get_all.call_count == 3
        # Each batch contains the right slice
        batch_sizes = [
            len(call.args[0][1])  # ("ARGS", tuple) → tuple
            for call in gpu_only_stub["mock_table"].return_value.get_all.call_args_list
        ]
        assert batch_sizes == [100, 100, 50]


class TestDeassignDesktopsWithGpu:
    """Companion to Bug 3 — the same flow on the ``domains`` table for
    desktops. Pins the index choice (``vgpus`` when ``desktops=None``)
    and the rewrite shape.
    """

    @pytest.fixture
    def gpu_only_stub(self, monkeypatch):
        from isardvdi_common.lib.bookings import reservables as mod

        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(
            mod.ResourceItemsGpus, "_rdb_context", classmethod(lambda cls: _Ctx())
        )
        monkeypatch.setattr(
            type(mod.ResourceItemsGpus),
            "_rdb_connection",
            property(lambda self: MagicMock(name="conn")),
        )
        mock_table = MagicMock(name="r.table")
        monkeypatch.setattr(mod.r, "table", mock_table)

        class _RowExpr:
            def has_fields(self, *_a, **_k):
                return self

            def __getitem__(self, key):
                return self

            def __le__(self, other):
                return self

            def __lt__(self, other):
                return self

            def __ge__(self, other):
                return self

            def __gt__(self, other):
                return self

            def __eq__(self, other):
                return self

            def __and__(self, other):
                return self

            def __or__(self, other):
                return self

            def default(self, _):
                return self

        monkeypatch.setattr(mod.r, "row", _RowExpr())
        monkeypatch.setattr(
            mod.r, "args", lambda x: ("ARGS", tuple(x) if hasattr(x, "__iter__") else x)
        )
        return {"mock_table": mock_table, "Cls": mod.ResourceItemsGpus}

    def test_uses_vgpus_index_when_no_desktop_list(self, gpu_only_stub):
        gpu_only_stub[
            "mock_table"
        ].return_value.get_all.return_value.filter.return_value.update.return_value.run.return_value = {
            "replaced": 0
        }
        gpu_only_stub["Cls"].deassign_desktops_with_gpu("NVIDIA-A40-1Q", None)
        # called with index="vgpus"
        gpu_only_stub["mock_table"].return_value.get_all.assert_called_with(
            "NVIDIA-A40-1Q", index="vgpus"
        )

    def test_targets_specific_desktops_when_provided(self, gpu_only_stub):
        gpu_only_stub[
            "mock_table"
        ].return_value.get_all.return_value.filter.return_value.update.return_value.run.return_value = {
            "replaced": 0
        }
        gpu_only_stub["Cls"].deassign_desktops_with_gpu("NVIDIA-A40-1Q", ["d1", "d2"])
        gpu_only_stub["mock_table"].return_value.get_all.assert_called_with(
            ("ARGS", ("d1", "d2"))
        )
