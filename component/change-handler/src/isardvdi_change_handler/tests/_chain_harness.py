# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared harness for tests that drive a REAL task chain end to end.

These tests exist because the defects they pin are properties of the *graph* —
which member can be reached from which, in which state — and a fixture that
builds the graph the test wants to see cannot fail. So the harness builds the
chain the product builds, with the product's own code, on a real Redis:

* the chain definition is captured from the real ``Storage`` builder,
* the rq graph is built by the real ``Task`` constructor,
* cancellation goes through the real ``Task.cancel``,
* and the event handed to the consumer is the one ``Task.cancel`` published.

Only the two edges this suite does not own are stubbed: the SocketIO feedback
emit, and the finalize handler bodies (they write to RethinkDB), replaced by
recorders so the assertions are about which members were reached.
"""

import os
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from isardvdi_common.helpers.task_streams import CANCELED_KIND, RESULT_STREAM
from isardvdi_common.models.storage import Storage
from redis import Redis

# The four rows a template creation touches, and that its terminal step must
# settle when the operation does not succeed.
DESKTOP_ID = "test-desktop-1"
TEMPLATE_ID = "test-template-1"
DESKTOP_STORAGE_ID = "test-desktop-storage-1"
TEMPLATE_STORAGE_ID = "test-template-storage-1"

# A scratch Redis db, never the rq db (0): these tests create, cancel and then
# destroy real rq jobs, and they flush the db they work on.
SCRATCH_DB = int(os.environ.get("TASK_CHAIN_TEST_REDIS_DB", "9"))

# Every finalize task name the template chain declares.
FINALIZE_TASKS = ("storage_update", "storage_update_parent", "update_status")


def scratch_connection():
    """A Redis handle on the scratch db, or ``None`` if there is no server.

    Explicit timeouts: an unresolvable host otherwise leaves the probe blocking
    on DNS for minutes, which turns "there is no Redis here, skip" into a hung
    job.
    """
    assert SCRATCH_DB != 0, "refusing to run against the live rq db"
    connection = Redis(
        host=os.environ.get("REDIS_HOST") or "isard-redis",
        port=int(os.environ.get("REDIS_PORT") or 6379),
        password=os.environ.get("REDIS_PASSWORD", ""),
        db=SCRATCH_DB,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    try:
        connection.ping()
    except Exception:
        return None
    return connection


def template_chain_kwargs():
    """The REAL template-creation chain definition, captured from the real
    builder.

    ``Storage.create_task`` is the only thing replaced: it is what would
    construct the ``Task``, and it also carries the 428 gate and the RethinkDB
    write of ``storage.task``, neither of which belongs in these tests.
    Everything about the *shape* of the chain — every queue, every task name,
    every nesting level — comes from
    ``Storage.enqueue_template_creation_chain_from_desktop`` itself, so the
    tests track the product instead of a copy of it.

    The caller must use the :func:`repair_storage_new_slot` fixture.
    """
    desktop_storage = Storage.__new__(Storage)
    object.__setattr__(desktop_storage, "id", DESKTOP_STORAGE_ID)
    object.__setattr__(desktop_storage, "directory_path", "/isard/groups")
    object.__setattr__(desktop_storage, "type", "qcow2")
    object.__setattr__(desktop_storage, "user_id", "test-user")
    object.__setattr__(desktop_storage, "parent", None)
    object.__setattr__(desktop_storage, "task", None)

    template_storage = MagicMock()
    template_storage.pool = MagicMock(id="dst-pool")
    template_storage.path = f"/isard/templates/{TEMPLATE_STORAGE_ID}.qcow2"
    template_storage.type = "qcow2"

    real_new = Storage.__new__

    def fake_new(cls, *args, **kwargs):
        if args and args[0] == TEMPLATE_STORAGE_ID:
            return template_storage
        return real_new(cls)

    with (
        patch.object(Storage, "create_task") as create_task,
        patch.object(Storage, "exists", return_value=True),
        patch.object(
            Storage,
            "pool",
            new_callable=PropertyMock,
            return_value=MagicMock(id="src-pool"),
        ),
        patch("isardvdi_common.models.storage.Storage.__new__", side_effect=fake_new),
        patch.object(
            Storage, "task", new_callable=PropertyMock, return_value=None, create=True
        ),
    ):
        desktop_storage.enqueue_template_creation_chain_from_desktop(
            desktop_id=DESKTOP_ID,
            template_id=TEMPLATE_ID,
            template_storage_id=TEMPLATE_STORAGE_ID,
        )

    kwargs = dict(create_task.call_args.kwargs)
    # ``blocking`` is consumed by ``create_task`` itself, not by ``Task``.
    kwargs.pop("blocking", None)
    return kwargs


def recording_handlers(ran):
    """Stand in for the finalize handler bodies (they write to RethinkDB).

    Each records the step the consumer dispatched to it, so the assertions are
    about which chain members were reached.
    """

    def make(name):
        def handler(step, **kwargs):
            ran.append((name, step.id, kwargs))

        return handler

    return {name: (make(name), False) for name in FINALIZE_TASKS}


def canceled_event(connection):
    """The cancel event ``Task.cancel`` itself published, as the consumer would
    read it off the stream."""
    entries = connection.xrange(RESULT_STREAM)
    assert entries, "Task.cancel published no event on the result stream"
    fields = {
        key.decode() if isinstance(key, bytes) else key: (
            value.decode() if isinstance(value, bytes) else value
        )
        for key, value in entries[-1][1].items()
    }
    assert fields.get("kind") == CANCELED_KIND, fields
    return fields


def finalize_nodes(job):
    """Every finalize node carried by ``job``'s meta, depth first.

    That includes the views of a knot child that will never be built: they are
    finalize steps that run, so anything asking "did this step's mark survive?"
    must count them too.
    """

    def walk(nodes):
        for node in nodes or []:
            yield node
            yield from walk(node.get("core_finalize"))
            for unbuilt in (node.get("unbuilt_knot_finalize") or {}).values():
                yield from walk(unbuilt)

    return list(walk(job.meta.get("core_finalize")))


def first_core_step(task):
    """The chain's first metadata finalize step, found by walking the real
    dependents from the root — i.e. the step that carries the knot.

    In the template chain that is the ``storage_update`` hanging off the third
    storage job; the walk finds it rather than the test asserting where it is.
    """
    from isardvdi_common.models.task import CoreStep

    frontier = [task]
    while frontier:
        current = frontier.pop(0)
        for dependent in current.dependents:
            if isinstance(dependent, CoreStep):
                return dependent
            frontier.append(dependent)
    raise AssertionError("the chain has no finalize step — the harness is broken")


def storage_jobs(connection):
    """Every rq job currently in the scratch db, by id."""
    from rq.job import Job

    jobs = {}
    for key in connection.keys("rq:job:*"):
        job_id = key.decode().split("rq:job:", 1)[1]
        if ":" in job_id:  # rq's per-job sub-keys (dependents, …)
            continue
        jobs[job_id] = Job.fetch(job_id, connection=connection)
    return jobs


@pytest.fixture
def repair_storage_new_slot():
    """``patch(..."Storage.__new__")`` leaves ``tp_new`` pointing at
    ``object.__new__`` even after the patch is undone, which breaks every later
    ``Storage(id)`` in the same interpreter. Reinstall a pass-through."""
    yield
    if "__new__" not in Storage.__dict__:
        Storage.__new__ = staticmethod(lambda cls, *args, **kwargs: object.__new__(cls))
