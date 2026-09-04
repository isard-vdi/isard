# SPDX-License-Identifier: AGPL-3.0-or-later

"""A promoted row must say who moved it, and not keep contradicting itself.

``_promote_domains_to_stopped`` wrote ``status`` alone, so the row kept the
``detail`` of whoever wrote it last. Promoted out of ``Failed``, it read as
ready while still carrying the reason it was not — measured on a production
install as five desktops in ``Stopped`` whose detail was a failure, two of them
with no ``xml`` at all and therefore unable to start.

Two changes come out of that. A promoted row now names the promotion and keeps
the previous text after it, so it stops contradicting itself. And ``Failed``
leaves the promotable set: this fires on the disk's news and cannot tell whether
the disk was the reason for the failure, so clearing one is right only by
accident — and the case that settles it produced the two dead desktops.
"""

from unittest.mock import MagicMock, patch

import pytest
from isardvdi_change_handler.task_results.storage import (
    _DOMAIN_PRE_READY_STATUSES,
    PROMOTED_DETAIL,
    _promote_domains_to_stopped,
    _promotion_detail,
)


class _Domain:
    """A row that records what is assigned to it, in order."""

    def __init__(self, status, detail=None):
        self.id = "d1"
        self.status = status
        self.detail = detail
        self.current_action = "something"
        self.writes = []

    def __setattr__(self, name, value):
        if name != "writes" and "writes" in self.__dict__:
            self.writes.append((name, value))
        object.__setattr__(self, name, value)


def _promote(domain):
    """Run the promotion and return the guarded write it issued, if any."""
    storage = MagicMock()
    storage.domains = [domain]
    with patch(
        "isardvdi_change_handler.task_results.storage.Domain.update_document_if"
    ) as write:
        _promote_domains_to_stopped(storage)
    if not write.called:
        return None
    assert write.call_args.kwargs["field"] == "status"
    assert write.call_args.kwargs["values"] == (domain.status,)
    return write.call_args.args[1]


class TestWhatTheRowSaysAfterwards:
    def test_a_promoted_row_names_the_promotion(self):
        written = _promote(_Domain("CreatingDomain", "waiting for the disk"))

        assert written["status"] == "Stopped"
        assert written["current_action"] is None
        assert written["detail"].startswith(PROMOTED_DETAIL)

    def test_it_keeps_the_previous_reason(self):
        written = _promote(_Domain("Maintenance", "sparsify in progress"))

        assert "was Maintenance" in written["detail"]
        assert "sparsify in progress" in written["detail"]

    def test_status_and_detail_land_in_one_write_guarded_on_the_read_status(self):
        """The engine and the chain's later steps write these statuses too."""
        domain = _Domain("Maintenance", "a reason")
        written = _promote(domain)

        assert set(written) == {"status", "current_action", "detail"}
        assert domain.writes == []

    def test_a_row_with_no_previous_detail_says_only_what_happened(self):
        written = _promote(_Domain("DiskNew", None))

        assert written["detail"] == f"{PROMOTED_DETAIL} (was DiskNew)"

    def test_a_failed_desktop_stays_failed(self):
        """The promotion fires on the disk's news and cannot know whether the
        disk was the reason for the failure, so it does not get to clear one.

        The case that settles it: the engine restarting mid-creation writes
        ``Failed``; the chain then finishes, and promoting would have produced
        a ``Stopped`` desktop with no ``xml`` — one that cannot start and no
        longer says so.
        """
        domain = _Domain("Failed", "Engine failed to build XML for start")

        assert _promote(domain) is None
        assert domain.writes == []

    def test_a_running_domain_is_not_touched_at_all(self):
        domain = _Domain("Started", "running")

        assert _promote(domain) is None
        assert domain.writes == []

    def test_a_very_long_previous_detail_is_bounded(self):
        written = _promote(_Domain("Maintenance", "x" * 500))

        assert len(written["detail"]) < 300
        assert written["detail"].endswith("…")


class TestTheHelperOnItsOwn:
    @pytest.mark.parametrize("previous", sorted(_DOMAIN_PRE_READY_STATUSES))
    def test_every_promotable_status_is_named_in_the_detail(self, previous):
        assert f"(was {previous})" in _promotion_detail(previous, None)

    @pytest.mark.parametrize("empty", [None, "", "None", "null", "   "])
    def test_an_empty_previous_detail_adds_nothing(self, empty):
        assert "previous detail" not in _promotion_detail("Maintenance", empty)

    def test_failed_is_not_promotable(self):
        assert "Failed" not in _DOMAIN_PRE_READY_STATUSES

    def test_the_marker_is_greppable(self):
        """A log or a database query is how anyone finds these rows."""
        assert PROMOTED_DETAIL and "\n" not in PROMOTED_DETAIL
