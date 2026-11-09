# SPDX-License-Identifier: AGPL-3.0-or-later

"""v216 seeds an empty costly-repair allowed list, keeps one an admin set, and never raises."""

import runpy
import types

from tests.helpers import SRC_ROOT

m = types.SimpleNamespace(
    **runpy.run_path(
        str(SRC_ROOT / "initdb" / "upgrade_helpers.py"),
        run_name="_storage_repair_allowed_under_test",
    )
)


class _Run:
    def __init__(self, value=None, error=None, on_run=None):
        self.value, self.error, self.on_run = value, error, on_run

    def run(self, conn):
        if self.error:
            raise self.error
        if self.on_run:
            self.on_run()
        return self.value


class FakeConfig:
    def __init__(self, doc=None, read_error=None, write_error=None):
        self.doc = doc if doc is not None else {"id": 1}
        self.read_error, self.write_error = read_error, write_error
        self.writes = []

    def get(self, item_id):
        assert item_id == 1
        return self

    def pluck(self, spec):
        assert spec == {"storage_repair": "allowed"}
        return self

    def default(self, value):
        doc = self.doc.get("storage_repair", {})
        out = (
            {"storage_repair": {"allowed": doc["allowed"]}} if "allowed" in doc else {}
        )
        return _Run(out, self.read_error)

    def update(self, change):
        return _Run(error=self.write_error, on_run=lambda: self.writes.append(change))


def test_a_config_without_the_list_gets_one_that_allows_nobody():
    config, warnings = FakeConfig(), []
    assert m.v216_storage_repair_allowed(config, None, warnings.append) is True
    assert config.writes == [
        {
            "storage_repair": {
                "allowed": {
                    "roles": False,
                    "categories": False,
                    "groups": False,
                    "users": False,
                }
            }
        }
    ]
    assert warnings == []


def test_the_seeded_list_matches_no_user_through_is_allowed():
    allowed = m.STORAGE_REPAIR_ALLOWED_EMPTY
    assert all(value is False for value in allowed.values())
    assert set(allowed) == {"roles", "categories", "groups", "users"}


def test_a_list_an_admin_already_set_is_kept():
    config = FakeConfig(
        {"id": 1, "storage_repair": {"allowed": {"roles": ["manager"]}}}
    )
    assert m.v216_storage_repair_allowed(config, None, print) is False
    assert config.writes == []


def test_an_unreadable_config_is_logged_and_not_written():
    config, warnings = FakeConfig(read_error=RuntimeError("down")), []
    assert m.v216_storage_repair_allowed(config, None, warnings.append) is False
    assert config.writes == []
    assert len(warnings) == 1 and "v216" in warnings[0] and "down" in warnings[0]


def test_a_failing_write_is_logged_and_never_raises():
    config, warnings = FakeConfig(write_error=RuntimeError("boom")), []
    assert m.v216_storage_repair_allowed(config, None, warnings.append) is False
    assert len(warnings) == 1 and "v216" in warnings[0] and "boom" in warnings[0]


def test_the_config_upgrade_runs_it_for_216():
    source = (SRC_ROOT / "initdb" / "upgrade.py").read_text(encoding="utf-8")
    config_branch = source[source.index("    def config(self, version):") :]
    config_branch = config_branch[: config_branch.index("HYPERVISORS TABLE UPGRADES")]
    assert "if version == 216:" in config_branch
    assert "v216_storage_repair_allowed(" in config_branch
