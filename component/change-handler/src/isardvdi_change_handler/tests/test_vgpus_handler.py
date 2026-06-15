# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from unittest.mock import AsyncMock

import pytest
from isardvdi_change_handler.tests.conftest import FakeRow


class TestVgpusHandler:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.vgpus import VgpusHandler

        sio = AsyncMock()
        return VgpusHandler(sio, "vgpus")

    @pytest.mark.asyncio
    async def test_emits_vgpu_data_from_additional_properties(self, handler):
        row = FakeRow(
            additional_properties={
                "id": "gpu0",
                "vgpu_profile": "nvidia-35",
                "changing_to_profile": False,
                "mdevs": {
                    "nvidia-35": {
                        "mdev1": {"domain_started": "desktop-1"},
                        "mdev2": {"domain_started": False},
                    }
                },
            },
        )
        await handler.on_insert(row)

        handler.socketio_server.emit.assert_awaited_once()
        call_args = handler.socketio_server.emit.call_args
        assert call_args[0][0] == "vgpu_data"

        payload = json.loads(call_args[0][1])
        assert payload["id"] == "gpu0"
        assert payload["vgpu_profile"] == "nvidia-35"
        assert payload["desktops_started"] == ["desktop-1"]
        assert payload["changing_to_profile"] is False

    @pytest.mark.asyncio
    async def test_no_active_profile(self, handler):
        row = FakeRow(additional_properties={"id": "gpu0"})
        await handler.on_insert(row)

        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["vgpu_profile"] is None
        assert payload["desktops_started"] == []

    @pytest.mark.asyncio
    async def test_profile_not_in_mdevs(self, handler):
        row = FakeRow(
            additional_properties={
                "id": "gpu0",
                "vgpu_profile": "nvidia-35",
                "mdevs": {"nvidia-40": {}},
            },
        )
        await handler.on_insert(row)

        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["desktops_started"] == []

    @pytest.mark.asyncio
    async def test_aggregates_multiple_mdevs_for_active_profile(self, handler):
        """Every mdev on the active profile with a non-False domain_started
        must appear in desktops_started; mdevs whose domain_started is False
        must be filtered out.
        """
        row = FakeRow(
            additional_properties={
                "id": "gpu1",
                "vgpu_profile": "profileA",
                "mdevs": {
                    "profileA": {
                        "m0": {"domain_started": "desk-1"},
                        "m1": {"domain_started": "desk-2"},
                        "m2": {"domain_started": False},
                    },
                },
            },
        )
        await handler.on_insert(row)

        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert sorted(payload["desktops_started"]) == ["desk-1", "desk-2"]

    @pytest.mark.asyncio
    async def test_mdevs_from_non_active_profile_are_ignored(self, handler):
        """mdevs living under a profile that isn't the active one must NOT
        contribute to desktops_started, even if their domain_started is set.
        """
        row = FakeRow(
            additional_properties={
                "id": "gpu1",
                "vgpu_profile": "profileA",
                "mdevs": {
                    "profileA": {"m0": {"domain_started": "desk-1"}},
                    "profileB": {"m1": {"domain_started": "desk-other"}},
                },
            },
        )
        await handler.on_insert(row)

        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["desktops_started"] == ["desk-1"]

    @pytest.mark.asyncio
    async def test_on_update_profile_change_emits_new_profile_started(self, handler):
        """A profile transition (profileA → profileB) must emit the mdevs
        belonging to profileB and propagate changing_to_profile.
        """
        old = FakeRow(
            additional_properties={
                "id": "gpu1",
                "vgpu_profile": "profileA",
                "mdevs": {},
            },
        )
        new = FakeRow(
            additional_properties={
                "id": "gpu1",
                "vgpu_profile": "profileB",
                "changing_to_profile": "profileB",
                "mdevs": {"profileB": {"m0": {"domain_started": "desk-x"}}},
            },
        )
        await handler.on_update(old, new)

        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["vgpu_profile"] == "profileB"
        assert payload["changing_to_profile"] == "profileB"
        assert payload["desktops_started"] == ["desk-x"]

    @pytest.mark.asyncio
    async def test_on_update_delegates_to_emit(self, handler):
        row = FakeRow(additional_properties={"id": "gpu0"})
        await handler.on_update(FakeRow(), row)
        handler.socketio_server.emit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_emits_vgpu_data_to_administrators_admins(self, handler):
        """Pin the namespace+room target for vgpu_data — admin-only."""
        row = FakeRow(additional_properties={"id": "gpu1", "vgpu_profile": None})
        await handler.on_insert(row)

        call = handler.socketio_server.emit.call_args
        assert call[0][0] == "vgpu_data"
        namespace = call[0][2] if len(call[0]) > 2 else call.kwargs.get("namespace")
        room = call[0][3] if len(call[0]) > 3 else call.kwargs.get("room")
        assert namespace == "/administrators"
        assert room == "admins"

    # ------------------------------------------------------------------
    # available_units — pool size of the active profile (origin/main 31e88b859)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_available_units_matches_active_pool_size(self, handler):
        """available_units must be the number of mdev slots in the active
        profile pool, regardless of how many are actually started."""
        row = FakeRow(
            additional_properties={
                "id": "gpu0",
                "vgpu_profile": "nvidia-35",
                "mdevs": {
                    "nvidia-35": {
                        "m0": {"domain_started": "desk-1"},
                        "m1": {"domain_started": False},
                        "m2": {"domain_started": False},
                        "m3": {"domain_started": False},
                    }
                },
            },
        )
        await handler.on_insert(row)

        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["available_units"] == 4
        assert payload["desktops_started"] == ["desk-1"]

    @pytest.mark.asyncio
    async def test_available_units_zero_when_no_active_profile(self, handler):
        """No active profile → empty pool → available_units = 0 (not None,
        not absent). Pin so the webapp's `typeof !== 'undefined'` guard
        always sees a number."""
        row = FakeRow(additional_properties={"id": "gpu0"})
        await handler.on_insert(row)

        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["available_units"] == 0

    @pytest.mark.asyncio
    async def test_available_units_zero_when_profile_not_in_mdevs(self, handler):
        row = FakeRow(
            additional_properties={
                "id": "gpu0",
                "vgpu_profile": "nvidia-35",
                "mdevs": {"nvidia-40": {"m0": {"domain_started": False}}},
            },
        )
        await handler.on_insert(row)

        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["available_units"] == 0

    @pytest.mark.asyncio
    async def test_available_units_updates_on_profile_transition(self, handler):
        """Profile change A (size 2) → B (size 6) emits available_units = 6
        so the webapp progress bar's denominator follows the new pool."""
        old = FakeRow(
            additional_properties={
                "id": "gpu1",
                "vgpu_profile": "small",
                "mdevs": {"small": {"m0": {}, "m1": {}}},
            },
        )
        new = FakeRow(
            additional_properties={
                "id": "gpu1",
                "vgpu_profile": "big",
                "changing_to_profile": "big",
                "mdevs": {
                    "big": {
                        "m0": {"domain_started": False},
                        "m1": {"domain_started": False},
                        "m2": {"domain_started": False},
                        "m3": {"domain_started": False},
                        "m4": {"domain_started": False},
                        "m5": {"domain_started": False},
                    },
                },
            },
        )
        await handler.on_update(old, new)

        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["available_units"] == 6

    @pytest.mark.asyncio
    async def test_operator_intent_fields_and_mismatch(self, handler):
        """Upstream !4496: requested_profile / operator_passthrough /
        last_apply_error are forwarded, and profile_mismatch flags an
        operator request the runtime has not realized (webui renders the
        fault row; never auto-resolved)."""
        row = FakeRow(
            additional_properties={
                "id": "gpu0",
                "vgpu_profile": "nvidia-35",
                "requested_profile": "nvidia-36",
                "operator_passthrough": True,
                "last_apply_error": "teardown_blocked: card still held",
                "mdevs": {},
            },
        )
        await handler.on_insert(row)

        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["requested_profile"] == "nvidia-36"
        assert payload["operator_passthrough"] is True
        assert payload["profile_mismatch"] is True
        assert payload["last_apply_error"] == "teardown_blocked: card still held"

    @pytest.mark.asyncio
    async def test_no_mismatch_when_request_matches_or_absent(self, handler):
        row = FakeRow(
            additional_properties={
                "id": "gpu0",
                "vgpu_profile": "nvidia-35",
                "requested_profile": "nvidia-35",
                "mdevs": {},
            },
        )
        await handler.on_insert(row)
        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["profile_mismatch"] is False
        assert payload["operator_passthrough"] is False

        handler.socketio_server.emit.reset_mock()
        row = FakeRow(additional_properties={"id": "gpu0", "mdevs": {}})
        await handler.on_insert(row)
        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["profile_mismatch"] is False
        assert payload["last_apply_error"] is None
