# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for api/schemas/common.py — base response models used across
every route. Keeping these tight means a schema regression in a shared
model fails loudly at unit-test time rather than silently breaking the
OpenAPI spec for 100+ endpoints.
"""

import pytest
from api.schemas.common import (
    DeleteResponse,
    EmptyResponse,
    ErrorResponse,
    PaginationResponseList,
    SimpleResponse,
    SimpleResponsePlural,
    UnauthorizedError,
)
from pydantic import BaseModel, ValidationError


class TestSimpleResponse:
    def test_accepts_string_id(self):
        assert SimpleResponse(id="abc").id == "abc"

    def test_rejects_missing_id(self):
        with pytest.raises(ValidationError):
            SimpleResponse()

    def test_rejects_none_id(self):
        with pytest.raises(ValidationError):
            SimpleResponse(id=None)


class TestSimpleResponsePlural:
    def test_accepts_list(self):
        assert SimpleResponsePlural(ids=["a", "b"]).ids == ["a", "b"]

    def test_rejects_missing(self):
        with pytest.raises(ValidationError):
            SimpleResponsePlural()

    def test_accepts_empty_list(self):
        # Bulk operations can legitimately return zero successful ids.
        assert SimpleResponsePlural(ids=[]).ids == []


class TestEmptyResponse:
    def test_no_fields(self):
        # OpenAPI emits {} for this — endpoints returning 200 w/ no body.
        assert EmptyResponse().model_dump() == {}


class TestDeleteResponse:
    def test_all_fields_optional(self):
        # None of message / message_code / tasks_ids are required.
        assert DeleteResponse().model_dump() == {
            "message": None,
            "message_code": None,
            "tasks_ids": None,
        }

    def test_accepts_all_fields(self):
        r = DeleteResponse(
            message="ok",
            message_code="deleted",
            tasks_ids=["t1", "t2"],
        )
        assert r.message == "ok"
        assert r.tasks_ids == ["t1", "t2"]


class TestErrorResponse:
    _full = {
        "error": "bad_request",
        "msg": "invalid value",
        "description_code": "bad_request",
        "function": "f",
        "function_call": "f()",
        "description": "desc",
        "debug": "",
        "request": "",
        "data": "",
        "params": None,
    }

    def test_accepts_full_payload(self):
        assert ErrorResponse(**self._full).error == "bad_request"

    def test_params_accepts_dict(self):
        payload = {**self._full, "params": {"key": "value", "count": 3}}
        assert ErrorResponse(**payload).params == {"key": "value", "count": 3}

    def test_missing_required_fails(self):
        # Drop a required field; ErrorResponse.params is Optional but all
        # string fields are required.
        for required in ("error", "msg", "description_code"):
            payload = {k: v for k, v in self._full.items() if k != required}
            with pytest.raises(ValidationError):
                ErrorResponse(**payload)


class TestUnauthorizedError:
    def test_detail_required(self):
        assert UnauthorizedError(detail="no token").detail == "no token"
        with pytest.raises(ValidationError):
            UnauthorizedError()


class TestPaginationResponseList:
    def test_string_generic_param(self):
        resp = PaginationResponseList[str](rows=["a", "b"], total=2)
        assert resp.rows == ["a", "b"]
        assert resp.total == 2

    def test_with_model_generic_param(self):
        class Row(BaseModel):
            id: str

        resp = PaginationResponseList[Row](rows=[Row(id="x")], total=1)
        assert resp.rows[0].id == "x"
        assert resp.total == 1

    def test_total_is_required(self):
        with pytest.raises(ValidationError):
            PaginationResponseList[str](rows=[])

    def test_rejects_negative_total_via_schema_extra_only(self):
        # Note: total has no lt=/gt= constraint in the current model. This
        # test pins the *current* behaviour — negative totals pass validation.
        # If a constraint is added later, invert this expectation.
        resp = PaginationResponseList[str](rows=[], total=-1)
        assert resp.total == -1
