# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared test fixtures and fake Pydantic models.

FakeRow mirrors the generated Row models' additional_properties
serialization behaviour: unknown fields are captured on parse and
merged back into the output on model_dump / model_dump_json.
"""

import os
import time
from typing import Any, Optional

import pytest
from pydantic import BaseModel, Field, model_serializer, model_validator

# Guards exclusive use of a scratch Redis db by one xdist worker at a time.
# The TTL is the crash hatch: a worker killed mid-test would otherwise wedge
# every later run on that db. The timeout is generous because a contending
# worker is waiting for a whole test, not a lock hold of a few milliseconds.
_SCRATCH_LOCK_KEY = "isard:test:chain-harness-lock"
_SCRATCH_LOCK_TTL_S = 300
_SCRATCH_LOCK_TIMEOUT_S = 120


class FakeRow(BaseModel):
    """Minimal Row model that behaves like the generated changefeed rows."""

    id: Optional[str] = None
    name: Optional[str] = None
    status: Optional[Any] = None
    kind: Optional[Any] = None
    user: Optional[str] = None
    category: Optional[str] = None
    table: Optional[str] = None
    tag: Optional[Any] = None
    tag_visible: Optional[bool] = None
    user_id: Optional[str] = None
    item_type: Optional[str] = None
    item_id: Optional[str] = None
    start: Optional[Any] = None
    end: Optional[Any] = None
    active: Optional[bool] = None
    hyp_started: Optional[str] = None
    persistent: Optional[bool] = None
    image: Optional[Any] = None
    create_dict: Optional[dict[str, Any]] = None
    vpn: Optional[Any] = None
    hostname: Optional[str] = None
    parent_category: Optional[str] = None
    additional_properties: Optional[dict[str, Any]] = Field(default=None, exclude=True)

    @model_serializer(mode="wrap")
    def custom_serializer(self, handler):
        serialized = handler(self)
        ap = getattr(self, "additional_properties")
        if ap is not None:
            for key, value in ap.items():
                if key not in serialized:
                    serialized[key] = value
        return serialized

    @model_validator(mode="before")
    @classmethod
    def unwrap_additional_properties(cls, data):
        if not isinstance(data, dict):
            data = data.model_dump()
        known = set(cls.model_fields.keys())
        unknown = [k for k in data if k not in known]
        if not unknown:
            return data
        ap = data.get("additional_properties") or {}
        for k in unknown:
            ap[k] = data.pop(k, None)
        data["additional_properties"] = ap
        return data


class FakeChange(BaseModel):
    """Minimal Change model that mirrors the generated changefeed changes."""

    new_val: Optional[FakeRow] = None
    old_val: Optional[FakeRow] = None


class FakeSocketIO:
    """Async socket.io server stub recording every emitted event."""

    def __init__(self):
        self.emitted: list[tuple[str, Any, str, Any]] = []

    async def emit(self, event, payload, namespace="/userspace", room=None):
        self.emitted.append((event, payload, namespace, room))


@pytest.fixture
def fake_socketio():
    return FakeSocketIO()


@pytest.fixture
def domain_row_factory():
    """Build FakeRow instances with sensible defaults for domain tests."""

    def _make(**overrides) -> FakeRow:
        defaults: dict[str, Any] = {
            "id": "d1",
            "name": "desktop-1",
            "user": "alice",
            "category": "default",
            "status": "Started",
            "kind": "desktop",
        }
        defaults.update(overrides)
        return FakeRow(**defaults)

    return _make


@pytest.fixture
def desktop_handler(fake_socketio):
    from isardvdi_change_handler.handlers.domains import DesktopDomainHandler

    return DesktopDomainHandler(fake_socketio)


@pytest.fixture
def media_row_factory():
    """Build FakeRow instances with sensible defaults for media tests."""

    def _make(**overrides) -> FakeRow:
        defaults: dict[str, Any] = {
            "id": "m1",
            "name": "media-1",
            "user": "u1",
            "category": "cat1",
            "status": "Downloaded",
        }
        defaults.update(overrides)
        return FakeRow(**defaults)

    return _make


@pytest.fixture
def media_handler(fake_socketio):
    from isardvdi_change_handler.handlers.media import MediaHandler

    return MediaHandler(fake_socketio, "media")


@pytest.fixture
def user_row_factory():
    from changefeed_models.users_row import UsersRow

    def _make(**overrides):
        defaults = dict(
            id="u-default",
            category="c-default",
            group="g-default",
            role="user",
            active=True,
            table="users",
        )
        return UsersRow(**{**defaults, **overrides})

    return _make


@pytest.fixture
def hypervisor_row_factory():
    from changefeed_models.hypervisors_row import HypervisorsRow

    def _make(**overrides):
        defaults = dict(
            id="h-default",
            status="Online",
            enabled=True,
            table="hypervisors",
        )
        return HypervisorsRow(**{**defaults, **overrides})

    return _make


@pytest.fixture
def users_handler(fake_socketio):
    from isardvdi_change_handler.handlers.users import UsersHandler

    return UsersHandler(fake_socketio, "users")


@pytest.fixture
def hypervisors_handler(fake_socketio):
    from isardvdi_change_handler.handlers.hypervisors import HypervisorsHandler

    return HypervisorsHandler(fake_socketio, "hypervisors")


@pytest.fixture
def scratch_redis():
    """A real Redis on a scratch db, or skip.

    rq's job graph (dependency sets, deferred registries, ``Job.cancel``, the
    Lua ``ended_at`` stamp) is not something a stub can stand in for without
    the stub becoming the thing under test — so the chain tests want a real
    server, and say so by skipping when there is none.
    """
    from isardvdi_change_handler.tests._chain_harness import scratch_connection

    connection = scratch_connection()
    if connection is None:
        pytest.skip("no Redis available for the real-chain harness")

    # Exclusive use of this db for the duration of the test. Each xdist worker
    # normally has a db to itself (see ``scratch_db``), so this lock is
    # uncontended — it exists for the case of more workers than the 15
    # available dbs, where two workers share one and would otherwise flush each
    # other's rq graph mid-test. Contending workers serialise instead.
    deadline = time.monotonic() + _SCRATCH_LOCK_TIMEOUT_S
    while not connection.set(
        _SCRATCH_LOCK_KEY, os.getpid(), nx=True, ex=_SCRATCH_LOCK_TTL_S
    ):
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"scratch redis db busy for {_SCRATCH_LOCK_TIMEOUT_S}s; a "
                "previous run may have died holding the lock (it expires "
                f"after {_SCRATCH_LOCK_TTL_S}s)"
            )
        time.sleep(0.05)

    # The clear is INSIDE the lock: it is the thing that must not land in
    # another worker's test. It is NOT ``flushdb`` — that would delete the lock
    # we are holding and let the next worker in while this test still runs.
    lock_key = _SCRATCH_LOCK_KEY.encode()

    def clear_but_keep_the_lock():
        keys = [key for key in connection.scan_iter("*") if key != lock_key]
        if keys:
            connection.delete(*keys)

    clear_but_keep_the_lock()
    try:
        yield connection
    finally:
        clear_but_keep_the_lock()
        connection.delete(_SCRATCH_LOCK_KEY)


@pytest.fixture
def task_on_scratch_redis(scratch_redis):
    """Point every ``Task`` (and the ``CoreStep`` views it hands out) at the
    scratch db for the duration of the test."""
    from isardvdi_common.models.task import Task

    original = Task.__dict__.get("_redis")
    Task._redis = scratch_redis
    try:
        yield scratch_redis
    finally:
        if original is None:
            del Task._redis
        else:
            Task._redis = original


@pytest.fixture(autouse=True)
def pinned_helper_returns(monkeypatch, request):
    if "no_pinned_helpers" in request.keywords:
        return
    from isardvdi_change_handler.tests._fixture_schemas import (
        CARD_USER,
        HYPERVISOR_DATA,
        MEDIA_ENRICHMENT,
        USER_ENRICHMENT,
    )

    patches = [
        (
            "isardvdi_common.lib.media.media.MediaProcessed.get_media_user_group_and_category_name",
            staticmethod(lambda _id: MEDIA_ENRICHMENT),
        ),
        (
            "isardvdi_common.lib.users.users.user.UsersProcessed.get_user_role_group_and_category_name",
            staticmethod(lambda _id: USER_ENRICHMENT),
        ),
        (
            "isardvdi_common.models.hypervisor.Hypervisor.get_hypervisor",
            staticmethod(lambda _id: dict(HYPERVISOR_DATA)),
        ),
        (
            "isardvdi_common.models.hypervisor.Hypervisor.count_started_desktops",
            staticmethod(lambda _id: 0),
        ),
        (
            "isardvdi_common.helpers.cards.Cards.delete_card",
            staticmethod(lambda _id: None),
        ),
        (
            "isardvdi_common.lib.domains.desktops.desktops.DesktopsProcessed.get_domain_enrichment",
            staticmethod(lambda _id: {}),
        ),
    ]
    for target, value in patches:
        try:
            monkeypatch.setattr(target, value, raising=False)
        except Exception:
            pass
