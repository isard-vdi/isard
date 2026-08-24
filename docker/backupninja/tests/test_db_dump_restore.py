"""End-to-end cover for the nightly database backup path.

WHY THIS EXISTS
---------------
No pipeline job had ever executed a database dump. ``docker-image`` builds the
backupninja image and nothing afterwards runs ``rethinkdb-dump`` against a
server, so a driver that could not dump at all still produced a green pipeline.
That is how the Python 3.14 ``multiprocessing`` breakage reached a release
branch: the code that broke is only reachable from a cron job nothing tested.

WHAT IT ASSERTS, AND WHY THAT SHAPE
-----------------------------------
Two rules drive the shape of these tests, and both come from how the defect
hides:

1. **Never against an empty database.** ``_export.run_clients`` builds one
   worker per ``db.table`` and forks nothing when there are no tables, so an
   empty database exits 0 through a driver that cannot dump a single row. Every
   test here seeds real tables with real rows first.

2. **Never trust the exit code.** ``rethinkdb-dump`` writes its archive before
   the workers report, so a truncated or empty archive can accompany a 0 exit.
   These tests decompress the archive and count the rows per table.

THE FAILURE THIS GUARDS AGAINST
-------------------------------
Python 3.14 changed the default ``multiprocessing`` start method on Linux from
``fork`` to ``forkserver``. ``forkserver`` pickles the arguments handed to
``Process``; the exporter passes its ``options`` object, which carries a
``RetryQuery`` holding a ``threading.local``. The result is::

    TypeError: cannot pickle '_thread._local' object

``fork`` inherited those arguments through memory and never serialized them,
which is why the same code worked on 3.13.
"""

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from pathlib import Path

import pytest
from rethinkdb import r

# host:port of a real RethinkDB. The CI job sets this; a developer exports it to
# run the suite locally. When it is unset the tests skip, because there is
# nothing to talk to — but see the connection fixture: once it IS set, an
# unreachable server is a failure, never a skip. A silent skip in CI would be
# the exact green-having-asserted-nothing outcome this file exists to prevent.
RETHINKDB_ADDRESS = os.environ.get("ISARD_TEST_RETHINKDB", "")

pytestmark = pytest.mark.skipif(
    not RETHINKDB_ADDRESS,
    reason="ISARD_TEST_RETHINKDB is unset; no server to dump from",
)

# Table name -> number of rows to seed. Deliberately uneven, and deliberately
# including an empty table: the archive must report 0 for it rather than omit
# it, and a dump whose row counting is off by a table boundary shows up here.
#
# The table count used to be a ceiling as well. A locked multiprocessing.Value
# allocates a POSIX semaphore and musl caps a process at 256, so five per table
# in the importer meant a restore of more than about fifty tables died in
# parse_sources with "OSError: [Errno 24] No file descriptors available" before
# reaching any Process at all. A real database has around sixty tables, so the
# restore path was broken on the Alpine images irrespective of the interpreter.
# The driver now takes a lock only for the counter several writers share, and
# test_restore_survives_a_realistic_table_count below is what keeps it that way:
# it seeds past the old ceiling on purpose.
SEED = {
    "users": 40,
    "domains": 25,
    "storage": 17,
    "categories": 6,
    "groups": 3,
    "recycle_bin": 0,
}


def _connect():
    host, _, port = RETHINKDB_ADDRESS.partition(":")
    return r.connect(host=host, port=int(port or 28015))


@pytest.fixture(scope="session")
def conn():
    """A live connection, or a hard failure.

    Explicitly not a skip: ISARD_TEST_RETHINKDB being set is a caller asserting
    that a server exists, so failing to reach it is a broken environment worth
    a red pipeline.
    """
    try:
        connection = _connect()
    except Exception as exc:  # noqa: BLE001 - surface the driver's own message
        pytest.fail(
            f"ISARD_TEST_RETHINKDB={RETHINKDB_ADDRESS} is set but unreachable: {exc}"
        )
    yield connection
    connection.close()


@pytest.fixture
def seeded_db(conn):
    """Create a uniquely-named database holding SEED, and drop it afterwards.

    Unique per test so a test that leaves the database dropped (the restore
    round-trip does exactly that, deliberately) cannot disturb another.
    """
    name = f"backup_probe_{uuid.uuid4().hex[:10]}"
    r.db_create(name).run(conn)
    for table, rows in SEED.items():
        r.db(name).table_create(table).run(conn)
        if rows:
            r.db(name).table(table).insert(
                [
                    # Wide-ish documents: a row that is a bare id would not
                    # notice a writer that truncates payloads.
                    {
                        "id": f"{table}-{i:04d}",
                        "name": f"{table} entry {i}",
                        "index": i,
                        "payload": "x" * 200,
                        "nested": {"table": table, "n": i},
                    }
                    for i in range(rows)
                ]
            ).run(conn)
    yield name
    try:
        r.db_drop(name).run(conn)
    except Exception:  # noqa: BLE001 - the restore test drops it itself
        pass


def _binary(name):
    path = shutil.which(name)
    if not path:
        pytest.fail(
            f"{name} is not on PATH; the rethinkdb driver's console scripts are "
            "part of what this suite exercises"
        )
    return path


def _run(args):
    """Run a rethinkdb-* command, returning the completed process.

    Never raises on a non-zero exit: each test decides what a failure means and
    reports the driver's own stderr, which carries the traceback that names the
    defect.
    """
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=600,
    )


def _live_counts(conn, db):
    return {t: r.db(db).table(t).count().run(conn) for t in SEED}


def _archive_counts(archive):
    """Row count per table read out of the dump archive itself.

    The archive holds ``<dump-dir>/<db>/<table>.json``, each a JSON array of
    documents. Counting these is the whole point: an exit code cannot tell an
    empty archive from a full one.
    """
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(archive) as tar:
            tar.extractall(tmp)
        counts = {}
        for path in Path(tmp).rglob("*.json"):
            if path.name == "info.json":
                continue
            counts[path.stem] = len(json.loads(path.read_text()))
        return counts


def test_dump_archive_holds_every_seeded_row(conn, seeded_db, tmp_path):
    """rethinkdb-dump must produce an archive whose contents match the server.

    This is the test that goes red on the old driver: exporting even one table
    under forkserver dies pickling ``options``, so no archive is written at all.
    """
    archive = tmp_path / "dump.tar.gz"

    result = _run(
        [
            _binary("rethinkdb-dump"),
            "-c",
            RETHINKDB_ADDRESS,
            "-e",
            seeded_db,
            "-f",
            str(archive),
        ]
    )

    assert result.returncode == 0, (
        "rethinkdb-dump failed.\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "cannot pickle" not in result.stderr, (
        "rethinkdb-dump hit the multiprocessing start-method defect:\n"
        f"{result.stderr}"
    )
    assert archive.exists(), "rethinkdb-dump exited 0 without writing an archive"
    assert archive.stat().st_size > 0, "rethinkdb-dump wrote an empty archive"

    expected = _live_counts(conn, seeded_db)
    assert sum(expected.values()) > 0, "refusing to assert against an empty database"
    assert _archive_counts(archive) == expected


def test_restore_round_trips_every_row(conn, seeded_db, tmp_path):
    """Dump, drop the database, restore it, and compare row counts.

    A backup nobody can restore is not a backup, so this asserts the whole
    round-trip rather than the dump half.
    """
    archive = tmp_path / "roundtrip.tar.gz"
    expected = _live_counts(conn, seeded_db)

    dumped = _run(
        [
            _binary("rethinkdb-dump"),
            "-c",
            RETHINKDB_ADDRESS,
            "-e",
            seeded_db,
            "-f",
            str(archive),
        ]
    )
    assert (
        dumped.returncode == 0
    ), f"dump failed before restore could run:\n{dumped.stderr}"

    r.db_drop(seeded_db).run(conn)
    assert seeded_db not in r.db_list().run(conn)

    restored = _run(
        [_binary("rethinkdb-restore"), "-c", RETHINKDB_ADDRESS, str(archive)]
    )

    assert restored.returncode == 0, (
        "rethinkdb-restore failed.\n"
        f"--- stdout ---\n{restored.stdout}\n--- stderr ---\n{restored.stderr}"
    )
    assert seeded_db in r.db_list().run(
        conn
    ), "restore exited 0 without recreating the database"
    assert _live_counts(conn, seeded_db) == expected


def test_restore_survives_a_realistic_table_count(conn, tmp_path):
    """Restore a database with more tables than the old semaphore ceiling.

    Kept separate from the seeded fixture because what is under test here is the
    table COUNT, not the rows: each table costs the importer a set of shared
    counters, and it was the number of those -- not the volume of data -- that
    used to abort the restore. Sixty-odd tables is what a real deployment looks
    like, and it is above the ceiling that used to exist, so this fails loudly
    if a lock ever comes back to a per-table counter.
    """
    db = f"ceiling_{uuid.uuid4().hex[:8]}"
    r.db_create(db).run(conn)
    try:
        for i in range(70):
            table = f"t{i:03d}"
            r.db(db).table_create(table).run(conn)
            r.db(db).table(table).insert(
                [{"id": f"{table}-{j}"} for j in range(3)]
            ).run(conn)

        archive = tmp_path / "ceiling.tar.gz"
        dumped = _run(
            [
                _binary("rethinkdb-dump"),
                "-c",
                RETHINKDB_ADDRESS,
                "-e",
                db,
                "-f",
                str(archive),
            ]
        )
        assert dumped.returncode == 0, (
            "rethinkdb-dump failed on a realistic table count.\n"
            f"--- stderr ---\n{dumped.stderr}"
        )

        restored = _run(
            [
                _binary("rethinkdb-restore"),
                "-c",
                RETHINKDB_ADDRESS,
                "--force",
                str(archive),
            ]
        )
        assert "No file descriptors available" not in restored.stderr, (
            "restore hit the semaphore ceiling again: a per-table counter took a "
            f"lock back.\n--- stderr ---\n{restored.stderr}"
        )
        assert (
            restored.returncode == 0
        ), f"rethinkdb-restore failed.\n--- stderr ---\n{restored.stderr}"
        assert len(r.db(db).table_list().run(conn)) == 70
    finally:
        r.db_drop(db).run(conn)
