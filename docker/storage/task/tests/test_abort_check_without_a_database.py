# SPDX-License-Identifier: AGPL-3.0-or-later

"""The abort check when the storage worker cannot reach the database.

``isard-storage`` ships on nodes that have no ``isard-db``: the ``storage``,
``hypervisor`` and ``hypervisor-standalone`` flavours all include the storage
part and none of them includes the database one (``build.sh``). On those nodes
every ``Media(...)`` / ``Domain(...)`` lookup raises.

The abort check used to answer *"yes, abort"* to any failure. That set the
cancel watcher's event on entry, so curl was killed before its first byte, the
partial file was unlinked and the job raised ``CalledProcessError(130)`` — a
completed-looking cancellation. Every download on every remote node failed that
way.

A row that is provably gone must still abort; a database we simply cannot reach
must not.
"""

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


class _Unreachable(Exception):
    """Stands in for the driver's ReqlDriverError.

    The real one is ``rethinkdb.errors.ReqlDriverError``: *"Could not connect
    to isard-db:28015"*. Any non-:class:`ErrorBase` exception must be treated
    the same way, which is what this test pins.
    """


def _raising(exc):
    def _factory(_id):
        raise exc

    return _factory


@pytest.mark.parametrize(
    "check, model",
    [("_media_aborting", "Media"), ("_domain_aborting", "Domain")],
)
def test_an_unreachable_database_does_not_abort_the_download(monkeypatch, check, model):
    import task

    monkeypatch.setattr(task, model, _raising(_Unreachable("no route to isard-db")))

    assert getattr(task, check)("id-1") is False


@pytest.mark.parametrize(
    "check, model",
    [("_media_aborting", "Media"), ("_domain_aborting", "Domain")],
)
def test_a_row_that_is_gone_still_aborts_the_download(monkeypatch, check, model):
    import task

    monkeypatch.setattr(
        task,
        model,
        _raising(ErrorBase("not_found", "Document with id id-1 does not exist.")),
    )

    assert getattr(task, check)("id-1") is True


@pytest.mark.parametrize(
    "check, model",
    [("_media_aborting", "Media"), ("_domain_aborting", "Domain")],
)
def test_the_row_flag_still_aborts_when_the_database_answers(monkeypatch, check, model):
    import task

    class _Row:
        def __init__(self, _id):
            self.status = "DownloadAborting"

    monkeypatch.setattr(task, model, _Row)

    assert getattr(task, check)("id-1") is True


@pytest.mark.parametrize(
    "check, model",
    [("_media_aborting", "Media"), ("_domain_aborting", "Domain")],
)
def test_a_running_download_is_not_aborted(monkeypatch, check, model):
    import task

    class _Row:
        def __init__(self, _id):
            self.status = "Downloading"

    monkeypatch.setattr(task, model, _Row)

    assert getattr(task, check)("id-1") is False
