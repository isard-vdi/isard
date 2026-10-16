#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Index selection for the scoped visibility SET.

Asserts on the built ReQL rather than on a database: picking the wrong
index is silent at runtime — it still returns the right rows — but turns
a single-cell edit into a full scan of every user's desktops.
"""

from isardvdi_common.lib.deployments.deployment_desktops import (
    DeploymentDesktopsProcessed,
)

SELECT = DeploymentDesktopsProcessed._visibility_selection


def _reql(**kwargs):
    return repr(SELECT("dep-1", **kwargs))


def test_no_selector_scans_the_deployment_by_tag():
    query = _reql()
    assert "index='tag'" in query
    assert "{'kind': 'desktop'}" in query


def test_desktop_column_uses_the_compound_tag_index():
    query = _reql(tag_desktop_ids=["r1", "r2"])
    assert "index='tag_tag_desktop_id'" in query
    assert "['dep-1', 'r1']" in query
    assert "['dep-1', 'r2']" in query


def test_first_desktop_also_matches_legacy_rows():
    # Pre-release-184 domains carry ``tag_desktop_id: False`` and were
    # backfilled from create_dict[0], so targeting the first desktop has to
    # widen the key set or those rows are silently skipped.
    query = _reql(tag_desktop_ids=["r1"], legacy_tag_desktop_id="r1")
    assert "['dep-1', 'r1']" in query
    assert "['dep-1', False]" in query


def test_non_first_desktop_does_not_widen_to_legacy_rows():
    query = _reql(tag_desktop_ids=["r2"], legacy_tag_desktop_id="r1")
    assert "['dep-1', False]" not in query


def test_user_row_uses_kind_user_tag():
    query = _reql(users=["u1"])
    assert "index='kind_user_tag'" in query
    assert "['desktop', 'u1', 'dep-1']" in query


def test_single_cell_reads_the_user_not_the_desktop():
    # Both indexes return the same single row, but kind_user_tag reads
    # |desktops| rows (<=10) where tag_tag_desktop_id would read |users|
    # (potentially hundreds) to keep one.
    query = _reql(users=["u1"], tag_desktop_ids=["r1"])
    assert "index='kind_user_tag'" in query
    assert "index='tag_tag_desktop_id'" not in query
    assert "tag_desktop_id" in query  # residual filter


def test_desktop_ids_use_the_primary_key_and_stay_in_the_deployment():
    query = _reql(desktop_ids=["d1", "d2"])
    assert "index=" not in query
    assert "'tag': 'dep-1'" in query


def test_desktop_ids_win_over_the_rectangle_selectors():
    query = _reql(desktop_ids=["d1"], users=["u1"], tag_desktop_ids=["r1"])
    assert "index=" not in query
    assert "'u1'" not in query
