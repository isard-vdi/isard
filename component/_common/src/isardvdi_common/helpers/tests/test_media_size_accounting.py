#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Josep Maria Viñolas Auquer
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A media discovered by a storage scan has to count towards quota.

``generate_db_media`` builds the row for a media found on a hypervisor rather
than downloaded through the product. It wrote every progress key EXCEPT
``total_bytes`` — and that is the only one the accounting reads: quota
(``helpers/quotas.py``), analytics (``lib/analytics/analytics.py``) and the
usage pipeline (``lib/usage/media.py``) all sum ``progress.total_bytes``.

So every scan-discovered media counted as **zero bytes**, invisible to the
limits that decide whether a user may create more.

The size arrives the way curl prints it, so it has to be parsed. The rule the
parser follows is that a MISSING figure is better than a WRONG one: a missing
one reproduces today's behaviour, while a wrong one silently moves a quota.
"""

from isardvdi_common.helpers.helpers import Helpers

_parse = Helpers._bytes_from_human_size


class TestTheSizeIsReadTheWayCurlPrintsIt:
    def test_a_suffixed_size_becomes_bytes(self):
        assert _parse("3408k") == 3408 * 1024
        assert _parse("12M") == 12 * 1024**2
        assert _parse("2G") == 2 * 1024**3

    def test_a_fractional_size_is_kept(self):
        """curl prints "1.2G" as readily as "1200M"."""
        assert _parse("1.5M") == int(1.5 * 1024**2)

    def test_the_suffix_is_case_insensitive(self):
        assert _parse("4k") == _parse("4K")

    def test_bare_digits_are_bytes(self):
        assert _parse("4096") == 4096

    def test_a_number_passes_straight_through(self):
        assert _parse(3490290) == 3490290


class TestAMissingFigureRatherThanAWrongOne:
    """Every one of these would otherwise become a number that moves a quota."""

    def test_something_unparseable_is_not_guessed(self):
        assert _parse("unknown") is None
        assert _parse("--") is None

    def test_an_empty_or_absent_value_is_not_zero(self):
        """Zero is a claim about the disk; absence is an admission we do not
        know. Only the second is honest here."""
        assert _parse("") is None
        assert _parse("   ") is None
        assert _parse(None) is None

    def test_a_wrong_type_does_not_raise(self):
        """This runs inside a storage scan that must not fail over one row."""
        assert _parse(["3408k"]) is None
        assert _parse({"total": "3408k"}) is None
