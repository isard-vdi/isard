"""`--empty-tables`: carry a table with no rows instead of scrubbing its rows.

The point is not only privacy, it is cost: on a production-shaped dump the
three default tables are ~80% of the bytes, and emptying them skips the scrub,
the prune and the cross-table pass over all of it.
"""

from __future__ import annotations

import json
from pathlib import Path

from anonymize_db.cli import _empty_table, _scrub_dir_progress, build_parser
from anonymize_db.prune import DEFAULT_EMPTY_TABLES, parse_empty_tables
from anonymize_db.scrub import Scrubber


def test_flag_with_no_value_gives_the_defaults():
    p = build_parser()
    assert parse_empty_tables(p.parse_args([]).empty_tables) == ()
    assert (
        parse_empty_tables(p.parse_args(["--empty-tables"]).empty_tables)
        == DEFAULT_EMPTY_TABLES
    )


def test_flag_with_a_list_gives_that_list():
    p = build_parser()
    got = parse_empty_tables(p.parse_args(["--empty-tables", "a,b , c"]).empty_tables)
    assert got == ("a", "b", "c")
    # a trailing comma is not an error
    assert parse_empty_tables("a,b,") == ("a", "b")
    # an all-empty value falls back to the defaults rather than emptying nothing
    assert parse_empty_tables(" , ") == DEFAULT_EMPTY_TABLES


def test_help_renders():
    # argparse interpolates % in help strings, so a literal "80%" in one of
    # them makes --help raise TypeError. Nothing else in the suite renders the
    # help, so without this the break only shows up in front of a user.
    help_text = build_parser().format_help()
    assert "--empty-tables" in help_text
    for name in DEFAULT_EMPTY_TABLES:
        assert name in help_text


def _dump(tmp_path: Path, tables: dict[str, list[dict]]) -> Path:
    db = tmp_path / "rethinkdb_dump_x" / "isard"
    db.mkdir(parents=True)
    for name, rows in tables.items():
        (db / f"{name}.json").write_text(json.dumps(rows))
        (db / f"{name}.info").write_text(
            json.dumps(
                {"name": name, "primary_key": "id", "indexes": [{"index": "started"}]}
            )
        )
    return db


def test_emptied_table_keeps_its_info_and_loses_its_rows(tmp_path):
    db = _dump(
        tmp_path,
        {
            "logs_users": [{"id": f"l{i}", "request_ip": "10.1.2.3"} for i in range(5)],
            "users": [{"id": "u1", "email": "someone@realcorp.example"}],
        },
    )
    _scrub_dir_progress(db, Scrubber(seed=0), None, ("logs_users",))

    assert json.loads((db / "logs_users.json").read_text()) == []
    # the .info is what carries the primary key and the secondary indexes, so a
    # restore rebuilds the table complete — it simply has no rows
    info = json.loads((db / "logs_users.info").read_text())
    assert info["primary_key"] == "id"
    assert [i["index"] for i in info["indexes"]] == ["started"]

    # a table not named is scrubbed as usual, not emptied
    users = json.loads((db / "users.json").read_text())
    assert len(users) == 1
    assert users[0]["email"] != "someone@realcorp.example"


def test_naming_a_table_absent_from_the_dump_is_not_fatal(tmp_path, caplog):
    db = _dump(tmp_path, {"users": [{"id": "u1"}]})
    with caplog.at_level("WARNING"):
        _scrub_dir_progress(db, Scrubber(seed=0), None, ("logs_users", "nope"))
    assert json.loads((db / "users.json").read_text())
    assert "not present in this dump" in caplog.text


def test_empty_table_reports_the_row_count(tmp_path):
    db = _dump(tmp_path, {"logs_users": [{"id": f"l{i}"} for i in range(7)]})
    assert _empty_table(db / "logs_users.json") == 7
    assert json.loads((db / "logs_users.json").read_text()) == []
