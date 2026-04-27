# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/recycle_bin.py``."""

import pytest
from api.schemas.recycle_bin import (
    DeleteActionEnum,
    OldEntriesActionEnum,
    RecycleBinBulkRequest,
    RecycleBinBulkResponse,
    RecycleBinCutoffTimeResponse,
    RecycleBinEntriesResponse,
    RecycleBinLastAction,
    RecycleBinOldEntriesConfig,
    RecycleBinSetDefaultDeleteRequest,
    RecycleBinStatusResponse,
    RecycleBinSystemCutoffTimeResponse,
    RecycleBinUpdateCutoffTimeRequest,
    RecycleBinUpdateTaskRequest,
    UnusedItemTimeoutRule,
    UnusedItemTimeoutRuleCreateRequest,
    UnusedItemTimeoutRulesResponse,
    UnusedItemTimeoutRuleUpdateRequest,
)
from pydantic import ValidationError


class TestEnums:
    def test_delete_action_values(self):
        assert DeleteActionEnum.recycle.value == "recycle"
        assert DeleteActionEnum.permanent.value == "permanent"

    def test_old_entries_action_values(self):
        assert OldEntriesActionEnum.delete.value == "delete"
        assert OldEntriesActionEnum.keep.value == "keep"


class TestRecycleBinCutoffTimeResponse:
    def test_required(self):
        with pytest.raises(ValidationError):
            RecycleBinCutoffTimeResponse()


class TestRecycleBinLastAction:
    _required = {
        "action": "delete",
        "agent_category_id": "cat-a",
        "agent_category_name": "A",
        "agent_id": "u-1",
        "agent_name": "User",
        "agent_role": "admin",
        "agent_type": "user",
        "time": 1234567890,
    }

    @pytest.mark.parametrize("missing", list(_required))
    def test_every_field_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            RecycleBinLastAction(**payload)


class TestRecycleBinEntriesResponse:
    def test_entries_required(self):
        with pytest.raises(ValidationError):
            RecycleBinEntriesResponse()

    def test_accepts_empty(self):
        assert RecycleBinEntriesResponse(entries=[]).entries == []


class TestRecycleBinBulkRequest:
    def test_recycle_bin_ids_required(self):
        with pytest.raises(ValidationError):
            RecycleBinBulkRequest()

    def test_accepts_empty(self):
        r = RecycleBinBulkRequest(recycle_bin_ids=[])
        assert r.recycle_bin_ids == []


class TestRecycleBinBulkResponse:
    def test_default_empty_lists(self):
        r = RecycleBinBulkResponse()
        assert r.success == []
        assert r.failed == []


class TestRecycleBinStatusResponse:
    def test_defaults(self):
        r = RecycleBinStatusResponse()
        assert r.total == 0
        assert r.by_status == {}


class TestRecycleBinOldEntriesConfig:
    def test_all_optional(self):
        c = RecycleBinOldEntriesConfig()
        assert c.max_time is None
        assert c.action is None


class TestRecycleBinSetDefaultDeleteRequest:
    def test_rb_default_required(self):
        with pytest.raises(ValidationError):
            RecycleBinSetDefaultDeleteRequest()


class TestRecycleBinSystemCutoffTimeResponse:
    def test_required(self):
        """Note the schema typo: `recycle_bin_cuttoff_time` (two t's).
        The frontend depends on this exact key — pin so a future "fix"
        breaks loud here."""
        with pytest.raises(ValidationError):
            RecycleBinSystemCutoffTimeResponse()
        r = RecycleBinSystemCutoffTimeResponse(recycle_bin_cuttoff_time=86400)
        assert r.model_dump()["recycle_bin_cuttoff_time"] == 86400


class TestRecycleBinUpdateCutoffTimeRequest:
    def test_required(self):
        with pytest.raises(ValidationError):
            RecycleBinUpdateCutoffTimeRequest()


class TestRecycleBinUpdateTaskRequest:
    @pytest.mark.parametrize("missing", ["recycle_bin_id", "id", "status"])
    def test_required(self, missing):
        payload = {"recycle_bin_id": "rb-1", "id": "t-1", "status": "running"}
        del payload[missing]
        with pytest.raises(ValidationError):
            RecycleBinUpdateTaskRequest(**payload)


class TestUnusedItemTimeoutRule:
    def test_defaults(self):
        r = UnusedItemTimeoutRule()
        assert r.id is None
        assert r.name == ""
        assert r.timeout == 0
        assert r.enabled is True


class TestUnusedItemTimeoutRuleCreateRequest:
    @pytest.mark.parametrize("missing", ["name", "timeout"])
    def test_required(self, missing):
        payload = {"name": "Inactive", "timeout": 86400}
        del payload[missing]
        with pytest.raises(ValidationError):
            UnusedItemTimeoutRuleCreateRequest(**payload)


class TestUnusedItemTimeoutRuleUpdateRequest:
    def test_all_optional(self):
        u = UnusedItemTimeoutRuleUpdateRequest()
        assert u.name is None
        assert u.timeout is None


class TestUnusedItemTimeoutRulesResponse:
    def test_default_empty_list(self):
        r = UnusedItemTimeoutRulesResponse()
        assert r.rules == []
