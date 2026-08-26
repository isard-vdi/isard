# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin what apiv4 grafts onto uvicorn's access line.

uvicorn's ``record.args`` is only
``(client_addr, method, full_path, http_version, status_code)``; the identity,
duration and body arrive through ContextVars set in the request's own task.
Records are built by hand rather than by standing up a server.
"""

import contextvars
import json
import logging

import pytest
from api.dependencies.log_config import (
    RequestContextMiddleware,
    UvicornRecordFilter,
    _request_body,
    _request_start,
    set_request_identity,
)
from isardvdi_common.helpers.log import formatter
from isardvdi_common.helpers.redact import BODY_LIMIT, REDACTED

ACCESS_MSG = '%s - "%s %s HTTP/%s" %d'
ACCESS_ARGS = ("10.0.0.54:0", "GET", "/api/v4/desktops", "1.1", 200)

FULL_PAYLOAD = {
    "provider": "local",
    "user_id": "local-default-admin-admin",
    "role_id": "admin",
    "category_id": "default",
    "group_id": "default-default",
    "name": "Administrator",
}
# has_token_direct_viewer accepts viewer tokens, whose data is only
# category_id + desktop_id -- no user identity at all.
DIRECT_VIEWER_PAYLOAD = {"category_id": "default", "desktop_id": "abc"}
# has_token forces these two for kid == "isardvdi-hypervisors".
HYPERVISOR_PAYLOAD = {"role_id": "admin", "category_id": "*"}


@pytest.fixture
def root_level():
    """Restore the root level: these tests move it and xdist shares the process."""
    root = logging.getLogger()
    saved = root.level
    yield root
    root.setLevel(saved)


def _record(name, msg, args=(), **extra):
    record = logging.LogRecord(
        name=name,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )
    record.__dict__.update(extra)
    return record


def _emit(record):
    UvicornRecordFilter().filter(record)
    return json.loads(formatter.format(record))


def _captured(raw, size=None):
    """What ``RequestContextMiddleware`` leaves behind for the filter."""
    return {"data": bytearray(raw), "size": len(raw) if size is None else size}


def _access(
    payload,
    level=logging.INFO,
    args=ACCESS_ARGS,
    started=False,
    msg=ACCESS_MSG,
    captured=None,
):
    """Emit one access line with ``payload`` as the request's identity."""

    def run():
        logging.getLogger().setLevel(level)
        if payload is not None:
            set_request_identity(payload)
        if started:
            _request_start.set(0.0)
        if captured is not None:
            _request_body.set(captured)
        return _emit(_record("uvicorn.access", msg, args))

    # Each request gets its own context; mimic that so the ContextVars set here
    # cannot leak into another test.
    return contextvars.copy_context().run(run)


class TestIdentity:
    def test_all_four_ids_are_present(self, root_level):
        out = _access(FULL_PAYLOAD)
        assert out["user"] == {
            "user_id": "local-default-admin-admin",
            "role_id": "admin",
            "category_id": "default",
            "group_id": "default-default",
        }

    def test_identity_is_logged_at_info(self, root_level):
        """Routine attribution, as apiv3 did -- not gated behind DEBUG."""
        assert "user" in _access(FULL_PAYLOAD, logging.INFO)

    def test_only_the_identity_fields_are_taken(self, root_level):
        out = _access(FULL_PAYLOAD)
        assert "name" not in out["user"]
        assert "provider" not in out["user"]
        assert "Administrator" not in json.dumps(out)

    def test_the_access_fields_still_come_through(self, root_level):
        out = _access(FULL_PAYLOAD)
        assert out["status"] == 200
        assert out["logger"] == "uvicorn.access"
        assert out["request"] == {
            "method": "GET",
            "url": "/api/v4/desktops",
            "http_version": "1.1",
            "client_addr": "10.0.0.54:0",
        }

    def test_nothing_without_a_token(self, root_level):
        """open_router routes never authenticate, so the ContextVar is unset."""
        assert "user" not in _access(None)

    def test_lifecycle_records_never_gain_a_user(self, root_level):
        def run():
            set_request_identity(FULL_PAYLOAD)
            return _emit(_record("uvicorn.error", "Application startup complete."))

        out = contextvars.copy_context().run(run)
        assert "user" not in out
        assert out["logger"] == "uvicorn.error"


class TestPartialPayloads:
    def test_direct_viewer_carries_only_what_it_has(self, root_level):
        out = _access(DIRECT_VIEWER_PAYLOAD)
        assert out["user"] == {"category_id": "default"}

    def test_hypervisor_wildcard_category_survives(self, root_level):
        """`*` is a real value here, not a placeholder to filter out."""
        out = _access(HYPERVISOR_PAYLOAD)
        assert out["user"] == {"role_id": "admin", "category_id": "*"}

    def test_an_empty_payload_emits_no_user_key(self, root_level):
        assert "user" not in _access({"desktop_id": "abc"})


class TestDuration:
    def test_duration_is_reported_in_milliseconds(self, root_level):
        out = _access(None, started=True)
        assert isinstance(out["duration_ms"], float)
        assert out["duration_ms"] > 0

    def test_absent_when_the_middleware_did_not_run(self, root_level):
        """Better a missing field than a fabricated 0.0."""
        assert "duration_ms" not in _access(None, started=False)


class TestUrl:
    def test_the_query_string_is_stripped(self, root_level):
        """A `?jwt=` must never reach Loki, so nothing after `?` is kept."""
        out = _access(
            None,
            args=("10.0.0.54:0", "GET", "/api/v4/desktops?jwt=secret&x=1", "1.1", 200),
        )
        assert out["request"]["url"] == "/api/v4/desktops"
        assert "secret" not in json.dumps(out)

    def test_the_path_is_in_the_message(self, root_level):
        out = _access(None)
        assert out["msg"] == "GET /api/v4/desktops 200"


class TestMalformedRecords:
    def test_unexpected_args_are_passed_through_untouched(self, root_level):
        """uvicorn changing its access format must not take the service down."""
        out = _access(None, args=("only", "three", "things"), msg="%s %s %s")
        assert "request" not in out
        assert "status" not in out

    def test_a_record_with_no_args_survives(self, root_level):
        out = _access(None, args=())
        assert "request" not in out


class TestBodyOnTheAccessLine:
    PAYLOAD = b'{"username": "isard", "ssh_key": "PRIVATE"}'

    def test_body_is_logged_and_redacted_at_debug(self, root_level):
        out = _access(None, logging.DEBUG, captured=_captured(self.PAYLOAD))
        assert out["request"]["body"] == {"username": "isard", "ssh_key": REDACTED}
        assert "PRIVATE" not in json.dumps(out)

    def test_no_body_at_info(self, root_level):
        """The middleware would not have captured either; belt and braces."""
        out = _access(None, logging.INFO, captured=_captured(self.PAYLOAD))
        assert "body" not in out["request"]

    def test_no_body_when_nothing_was_captured(self, root_level):
        assert "body" not in _access(None, logging.DEBUG)["request"]

    def test_an_empty_body_emits_no_key(self, root_level):
        out = _access(None, logging.DEBUG, captured=_captured(b""))
        assert "body" not in out["request"]

    def test_non_json_is_dropped_rather_than_logged_raw(self, root_level):
        out = _access(
            None, logging.DEBUG, captured=_captured(b"username=isard&password=hunter2")
        )
        assert "body" not in out["request"]
        assert "hunter2" not in json.dumps(out)

    def test_oversized_is_summarised(self, root_level):
        out = _access(
            None,
            logging.DEBUG,
            captured=_captured(b'{"pad":"xxx"}', size=BODY_LIMIT + 500),
        )
        assert out["request"]["body"] == {"truncated": True, "size": BODY_LIMIT + 500}


class TestRequestContextMiddleware:
    @staticmethod
    def _scope(content_type=b"application/json"):
        return {
            "type": "http",
            "headers": [(b"content-type", content_type)] if content_type else [],
        }

    @staticmethod
    def _receive_from(chunks):
        queue = list(chunks)

        async def receive():
            body = queue.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(queue)}

        return receive

    async def _run(self, scope, chunks, level):
        logging.getLogger().setLevel(level)
        seen = {}

        async def app(scope, receive, send):
            # Drain the way a handler parsing the body would; the middleware
            # only ever captures what the app actually reads.
            while True:
                if not (await receive()).get("more_body"):
                    break
            seen["captured"] = _request_body.get()

        await RequestContextMiddleware(app)(scope, self._receive_from(chunks), None)
        return seen["captured"]

    async def test_json_body_is_captured_at_debug(self, root_level):
        captured = await self._run(self._scope(), [b'{"a": 1}'], logging.DEBUG)
        assert bytes(captured["data"]) == b'{"a": 1}'
        assert captured["size"] == 8

    async def test_nothing_is_captured_at_info(self, root_level):
        assert await self._run(self._scope(), [b'{"a": 1}'], logging.INFO) is None

    async def test_a_charset_suffix_still_counts_as_json(self, root_level):
        captured = await self._run(
            self._scope(b"application/json; charset=utf-8"),
            [b'{"a": 1}'],
            logging.DEBUG,
        )
        assert captured is not None

    async def test_uploads_never_enter_the_capture_path(self, root_level):
        """multipart/octet-stream must keep streaming untouched."""
        for ctype in (b"multipart/form-data; boundary=x", b"application/octet-stream"):
            assert await self._run(self._scope(ctype), [b"x"], logging.DEBUG) is None

    async def test_a_missing_content_type_is_skipped(self, root_level):
        assert await self._run(self._scope(None), [b'{"a": 1}'], logging.DEBUG) is None

    async def test_capture_is_capped_but_size_counts_everything(self, root_level):
        captured = await self._run(
            self._scope(), [b"x" * 5000, b"y" * 5000], logging.DEBUG
        )
        assert len(captured["data"]) == BODY_LIMIT
        assert captured["size"] == 10000

    async def test_http_scope_stamps_the_start(self):
        seen = {}

        async def app(scope, receive, send):
            seen["start"] = _request_start.get()

        await RequestContextMiddleware(app)(self._scope(None), None, None)
        assert seen["start"] is not None

    async def test_non_http_scope_is_passed_straight_through(self):
        """Lifespan and websocket scopes produce no access line to annotate."""
        seen = {}

        async def app(scope, receive, send):
            seen["start"] = _request_start.get()

        await RequestContextMiddleware(app)({"type": "lifespan"}, None, None)
        assert seen["start"] is None


def test_identity_does_not_leak_between_contexts(root_level):
    """Each request runs in its own task, hence its own context."""
    first = contextvars.copy_context()
    first.run(set_request_identity, FULL_PAYLOAD)

    second = contextvars.copy_context()
    out = second.run(lambda: _emit(_record("uvicorn.access", ACCESS_MSG, ACCESS_ARGS)))
    assert "user" not in out
