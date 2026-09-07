# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the recycle-bin retention guards."""

from datetime import datetime, timedelta, timezone

import pytest
from isardvdi_common.helpers.recycle_bin import Helpers


@pytest.fixture
def config(monkeypatch):
    """Serve a recycle-bin ``old_entries`` config without touching rdb."""

    def _set(**fields):
        row = {"max_time": None, "action": None, **fields}
        monkeypatch.setattr(
            Helpers, "get_old_entries_config", classmethod(lambda cls: row)
        )
        return row

    return _set


class TestGetOldEntriesCutoff:
    def test_a_positive_window_gives_a_cutoff_in_the_past(self, config):
        config(max_time=24)
        cutoff = Helpers.get_old_entries_cutoff()
        now = datetime.now(timezone.utc).timestamp()
        assert cutoff < now
        # ~24h back, generous slack so the assertion is about the direction
        # and the magnitude, not about clock precision.
        assert 23 * 3600 < now - cutoff < 25 * 3600

    @pytest.mark.parametrize("hours", [-1, -5])
    def test_a_negative_window_yields_no_cutoff(self, config, hours):
        """A window in the future has no meaning and no caller."""
        config(max_time=hours)
        assert Helpers.get_old_entries_cutoff() is None

    def test_a_zero_window_still_means_immediately(self, config):
        """The admin page offers 0 as "Immediately"; it must keep selecting."""
        config(max_time=0)
        cutoff = Helpers.get_old_entries_cutoff()
        assert cutoff is not None
        assert abs(cutoff - datetime.now(timezone.utc).timestamp()) < 5

    def test_a_window_that_overflows_timedelta_yields_no_cutoff(self, config):
        """The arithmetic must not be what fails; the answer is "nothing is
        that old", not an exception on every scheduled run."""
        config(max_time=999999999999)
        with pytest.raises(OverflowError):
            datetime.now(timezone.utc) - timedelta(hours=999999999999)
        assert Helpers.get_old_entries_cutoff() is None

    def test_an_unparseable_window_yields_no_cutoff(self, config):
        config(max_time="whenever")
        assert Helpers.get_old_entries_cutoff() is None

    def test_no_window_configured_yields_no_cutoff(self, config):
        config()
        assert Helpers.get_old_entries_cutoff() is None


class TestCheckOlderThanOldEntryMaxTime:
    @pytest.mark.parametrize("hours", [-1, -5])
    def test_a_negative_window_calls_nothing_old(self, config, hours):
        """The same guard has to hold for the per-entry reader."""
        config(max_time=hours)
        just_now = datetime.now(timezone.utc).timestamp()
        assert Helpers.check_older_than_old_entry_max_time(just_now) is False

    def test_a_zero_window_calls_an_existing_entry_old(self, config):
        config(max_time=0)
        a_moment_ago = datetime.now(timezone.utc).timestamp() - 1
        assert Helpers.check_older_than_old_entry_max_time(a_moment_ago) is True

    def test_a_positive_window_still_recognises_an_old_entry(self, config):
        config(max_time=1)
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
        assert Helpers.check_older_than_old_entry_max_time(two_hours_ago) is True


class TestOldEntriesPurgeEnabled:
    def test_only_delete_enables_the_purge(self, config):
        config(action="delete")
        assert Helpers.old_entries_purge_enabled() is True

    @pytest.mark.parametrize("action", ["keep", "none", None])
    def test_any_other_action_disables_the_purge(self, config, action):
        """``keep`` is what the api offers and ``none`` what the scheduler
        view takes; neither may leave the purge running."""
        config(action=action)
        assert Helpers.old_entries_purge_enabled() is False


class TestGetOldDeletedEntryIds:
    @pytest.mark.parametrize("hours", [-5, 999999999999, "whenever"])
    def test_a_dangerous_window_selects_nothing_and_never_queries(
        self, config, monkeypatch, hours
    ):
        """The selection is the last point before the delete, so prove it
        returns empty *and* that it does not even reach the database."""
        config(max_time=hours, action="delete")
        import isardvdi_common.helpers.recycle_bin as mod

        queried = []
        monkeypatch.setattr(mod.r, "table", lambda name: queried.append(name))

        assert Helpers.get_old_deleted_entry_ids() == []
        assert queried == []
