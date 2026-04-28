# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/socketio_emit.py — admin-triggered SocketIO event
broadcast.

After the Category A1 typed-body migration (see
``docs/plans/2026-04-23-apiv4-04-schema-completion.md``), the route
takes ``AdminSocketioEmitRequest`` (a ``RootModel[List[...]]``), so:

  - non-array bodies → 400 (apiv4 reshapes FastAPI's default 422 via
    its ``RequestValidationError`` handler into the legacy envelope)
  - the service receives ``List[SocketioEmitRequest]`` typed models
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/socketio
# ══════════════════════════════════════════════════════════════════════════


class TestEmitHappyPath:
    URL = "/admin/socketio"

    def test_admin_emits_events(self, monkeypatch, test_client):
        captured = {}

        def fake_emit(events):
            captured["events"] = events

        monkeypatch.setattr(
            "api.routes.admin.socketio_emit.AdminSocketioService.emit_events",
            staticmethod(fake_emit),
        )
        events = [
            {"event": "foo", "data": {"a": 1}, "namespace": "/", "room": "admins"},
            {"event": "bar", "data": {"b": 2}},
        ]
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=events,
        )
        assert response.status_code == 200
        assert response.json() == {}
        # The service now receives typed ``SocketioEmitRequest`` models;
        # compare via ``model_dump`` to keep equality with the raw input.
        assert [e.model_dump(exclude_none=True) for e in captured["events"]] == events

    def test_single_element_body(self, monkeypatch, test_client):
        """A one-element body works end-to-end. The empty-array path is
        exercised in the service unit tests; the conftest helper skips
        falsy bodies (``if body:``) so we can't send ``[]`` here.
        """
        captured = {}

        def fake_emit(events):
            captured["events"] = events

        monkeypatch.setattr(
            "api.routes.admin.socketio_emit.AdminSocketioService.emit_events",
            staticmethod(fake_emit),
        )
        events = [{"event": "noop"}]
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=events,
        )
        assert response.status_code == 200
        assert [e.model_dump(exclude_none=True) for e in captured["events"]] == events


class TestEmitInvalidBody:
    URL = "/admin/socketio"

    def test_non_list_body_returns_400(self, monkeypatch, test_client):
        """Body must be a JSON array. The typed ``RootModel[List[...]]``
        rejects a dict body BEFORE the route runs — apiv4 installs a
        ``RequestValidationError`` handler that reshapes FastAPI's default
        422 into the legacy 400 envelope, so the service must not be reached
        and the client sees 400.
        """
        called = {}

        def should_not_run(events):
            called["yes"] = True

        monkeypatch.setattr(
            "api.routes.admin.socketio_emit.AdminSocketioService.emit_events",
            staticmethod(should_not_run),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"event": "wrong-shape"},
        )
        assert response.status_code == 400
        assert called == {}


class TestEmitAuth:
    URL = "/admin/socketio"

    def test_manager_forbidden(self, monkeypatch, test_client):
        """admin_router endpoint — managers can NOT emit cross-cutting
        socketio events. Without this gate, a manager could broadcast
        to any room (admins, other categories, etc.).
        """
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.socketio_emit.AdminSocketioService.emit_events",
            staticmethod(lambda events: called.update(yes=True)),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body=[{"event": "x"}],
        )
        assert response.status_code == 403
        assert called == {}

    def test_user_forbidden(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.socketio_emit.AdminSocketioService.emit_events",
            staticmethod(lambda events: called.update(yes=True)),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body=[{"event": "x"}],
        )
        assert response.status_code == 403
        assert called == {}


class TestEmitErrorPropagation:
    URL = "/admin/socketio"

    def test_typed_error_propagates(self, monkeypatch, test_client):
        def reject(events):
            raise Error("bad_request", "Malformed event payload")

        monkeypatch.setattr(
            "api.routes.admin.socketio_emit.AdminSocketioService.emit_events",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=[{"event": "x"}],
        )
        assert response.status_code == 400

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom(events):
            raise RuntimeError("SocketIO server unreachable")

        monkeypatch.setattr(
            "api.routes.admin.socketio_emit.AdminSocketioService.emit_events",
            staticmethod(boom),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=[{"event": "x"}],
        )
        assert response.status_code == 500
        assert response.json().get("error") == "internal_server"
