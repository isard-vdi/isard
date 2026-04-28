"""Contract tests for the error wrapper."""

import json
from dataclasses import dataclass
from http import HTTPStatus

import pytest
from isardvdi_apiv4_client_auth._errors import ApiV4Error, raise_for_status


@dataclass
class _FakeResponse:
    """Minimal stand-in matching openapi-python-client's ``Response`` shape."""

    status_code: HTTPStatus
    content: bytes
    parsed: object = None


def test_2xx_passthrough():
    resp = _FakeResponse(status_code=HTTPStatus.OK, content=b"{}")
    raise_for_status(resp)  # should NOT raise


def test_4xx_raises_with_body():
    body = {
        "error": "not_found",
        "description": "gone",
        "description_code": "not_found_code",
    }
    resp = _FakeResponse(
        status_code=HTTPStatus.NOT_FOUND,
        content=json.dumps(body).encode(),
    )
    with pytest.raises(ApiV4Error) as exc_info:
        raise_for_status(resp)
    err = exc_info.value
    assert err.status_code == 404
    assert err.error == "not_found"
    assert err.description == "gone"
    assert err.description_code == "not_found_code"


def test_5xx_raises():
    resp = _FakeResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=b'{"error":"internal","description":"boom"}',
    )
    with pytest.raises(ApiV4Error) as exc_info:
        raise_for_status(resp)
    assert exc_info.value.status_code == 500


def test_non_json_body_still_raises():
    resp = _FakeResponse(
        status_code=HTTPStatus.BAD_GATEWAY,
        content=b"<html>upstream down</html>",
    )
    with pytest.raises(ApiV4Error) as exc_info:
        raise_for_status(resp)
    err = exc_info.value
    assert err.status_code == 502
    assert err.error == "http_error"  # fallback
    assert "<html>" in err.description


def test_maintenance_sentinel():
    resp = _FakeResponse(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        content=b'{"error":"maintenance","description":"down for maintenance"}',
    )
    with pytest.raises(ApiV4Error) as exc_info:
        raise_for_status(resp)
    assert exc_info.value.is_maintenance is True


def test_apiv4error_str_includes_useful_fields():
    err = ApiV4Error(
        status_code=400,
        error="bad_request",
        description="invalid body",
        description_code="validation_failed",
    )
    s = str(err)
    assert "400" in s
    assert "bad_request" in s
    assert "invalid body" in s
