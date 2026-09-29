#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Which card files the sweep counts as claimed, with the bin as an owner."""

import pytest
from isardvdi_common.helpers import cards as mod


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def pluck(self, *a, **k):
        return self

    def get_all(self, *args, index=None):
        # The selection is honoured on purpose: a stub that ignored it would pass
        # with the status filter deleted from the source, and prove nothing.
        wanted = set()
        for a in args:
            wanted |= set(a) if isinstance(a, (list, tuple, set)) else {a}
        assert index == "status", f"unexpected index {index!r}"
        return _Query([row for row in self._rows if row.get("status") in wanted])

    def run(self, _conn):
        return list(self._rows)


class _R:
    def __init__(self, domains, bin_entries):
        self._tables = {"domains": domains, "recycle_bin": bin_entries}

    def table(self, name):
        return _Query(self._tables[name])

    def args(self, xs):
        return list(xs)


@pytest.fixture
def wire(monkeypatch):
    def _wire(domains, bin_entries):
        monkeypatch.setattr(mod.Cards, "_rdb_context", classmethod(lambda cls: _Ctx()))
        monkeypatch.setattr(
            type(mod.Cards), "_rdb_connection", property(lambda self: None)
        )
        monkeypatch.setattr(mod, "r", _R(domains, bin_entries))
        return mod.Cards._referenced_card_files()

    return _wire


_LIVE = {"id": "live-1", "image": {"id": "live-1.jpg", "type": "user"}}
_BINNED = {"id": "binned-1", "image": {"id": "binned-1.jpg", "type": "user"}}
_BINNED_TPL = {"id": "tpl-1", "image": {"id": "tpl-1.jpg", "type": "user"}}


def _entry(status="recycled", **kwargs):
    return {"status": status, **kwargs}


class TestTheBinStillClaimsItsCards:
    def test_a_binned_desktop_keeps_its_card(self, wire):
        """The case that loses data: restore would find the file gone."""
        claimed = wire(domains=[], bin_entries=[_entry(desktops=[_BINNED])])

        assert "binned-1.jpg" in claimed

    def test_a_binned_template_keeps_its_card_too(self, wire):
        """``restore()`` re-inserts templates as well, so they own a card as much."""
        claimed = wire(domains=[], bin_entries=[_entry(templates=[_BINNED_TPL])])

        assert claimed == ["tpl-1.jpg"]

    def test_a_binned_template_with_a_stock_card_claims_nothing(self, wire):
        stock = {"id": "tpl-2", "image": {"id": "stock.jpg", "type": "stock"}}
        claimed = wire(domains=[], bin_entries=[_entry(templates=[stock])])

        assert claimed == []

    @pytest.mark.parametrize("status", ["recycled", "restored", "queued", "deleting"])
    def test_every_status_a_restore_can_come_back_from_still_claims(self, wire, status):
        claimed = wire(domains=[], bin_entries=[_entry(status, desktops=[_BINNED])])

        assert claimed == ["binned-1.jpg"]

    def test_a_permanently_deleted_entry_releases_it(self, wire):
        """Once it cannot be restored the card is free — and the entry is a real
        one, so removing the status selection from the source fails this."""
        claimed = wire(
            domains=[],
            bin_entries=[
                _entry("deleted", desktops=[_BINNED], templates=[_BINNED_TPL])
            ],
        )

        assert claimed == []

    def test_live_desktops_are_still_claimed(self, wire):
        claimed = wire(domains=[_LIVE], bin_entries=[])

        assert claimed == ["live-1.jpg"]

    def test_both_sources_are_merged_without_duplicates(self, wire):
        claimed = wire(
            domains=[_LIVE],
            bin_entries=[_entry(desktops=[_BINNED]), _entry(desktops=[_LIVE])],
        )

        assert sorted(claimed) == ["binned-1.jpg", "live-1.jpg"]

    def test_stock_cards_are_not_claimed_from_the_bin(self, wire):
        """Only user uploads live in USERS_CARDS; stock ones are shared."""
        stock = {"id": "b", "image": {"id": "stock.jpg", "type": "stock"}}
        claimed = wire(domains=[], bin_entries=[_entry(desktops=[stock])])

        assert claimed == []

    def test_an_entry_with_neither_list_is_harmless(self, wire):
        claimed = wire(
            domains=[], bin_entries=[_entry(desktops=None, templates=None), _entry()]
        )

        assert claimed == []


class TestPathsDoNotDependOnWhoImports:
    """The names must exist in every process, and importing must not create
    directories in one that never touches cards."""

    def test_the_paths_are_defined_without_an_api_module(self):
        assert mod.USERS_CARDS and mod.STOCK_CARDS

    def test_they_sit_under_one_configurable_root(self):
        assert mod.USERS_CARDS.startswith(mod.CARDS_ROOT)
        assert mod.STOCK_CARDS.startswith(mod.CARDS_ROOT)

    def test_importing_creates_nothing(self, tmp_path, monkeypatch):
        """Re-import with a root that does not exist: it must stay that way."""
        import importlib

        arrel = tmp_path / "no-existeix"
        monkeypatch.setenv("CARDS_ROOT", str(arrel))
        importlib.reload(mod)
        try:
            assert not arrel.exists(), "importing cards.py created its directories"
        finally:
            monkeypatch.delenv("CARDS_ROOT", raising=False)
            importlib.reload(mod)

    def test_the_directories_are_created_at_the_point_of_use(
        self, tmp_path, monkeypatch
    ):
        import importlib

        arrel = tmp_path / "cards"
        monkeypatch.setenv("CARDS_ROOT", str(arrel))
        importlib.reload(mod)
        try:
            mod._ensure_card_dirs()
            assert (arrel / "user").is_dir() and (arrel / "stock").is_dir()
        finally:
            monkeypatch.delenv("CARDS_ROOT", raising=False)
            importlib.reload(mod)
