#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the pure storage-pool path helpers
(``isardvdi_common.lib.storage.storage_pools.paths``).

These cover the optional ``{category}`` placeholder that lets an admin put the
tier *before* the category in a pool's per-usage subpath, and the reverse
matcher that resolves a usage from an on-disk path. Pure functions, no DB.
"""

from isardvdi_common.lib.storage.storage_pools.paths import (
    CATEGORY_TOKEN,
    build_category_pool_dir,
    usage_subpath_matches,
)

MP = "/isard/storage_pools/pool-a"


# --------------------------------------------------------------------------- #
# CATEGORY_TOKEN
# --------------------------------------------------------------------------- #
def test_category_token_value():
    assert CATEGORY_TOKEN == "{category}"


# --------------------------------------------------------------------------- #
# build_category_pool_dir  (forward)
# --------------------------------------------------------------------------- #
def test_build_legacy_no_token_inserts_category_after_mountpoint():
    # Backward compatible: no token => category right after the mountpoint.
    assert build_category_pool_dir(MP, "cat-a", "templates") == f"{MP}/cat-a/templates"


def test_build_legacy_multi_segment_subpath():
    assert (
        build_category_pool_dir(MP, "cat-a", "fast/templates")
        == f"{MP}/cat-a/fast/templates"
    )


def test_build_token_puts_tier_before_category():
    # The whole point: <mountpoint>/fast/<category>/templates
    assert (
        build_category_pool_dir(MP, "cat-a", "fast/{category}/templates")
        == f"{MP}/fast/cat-a/templates"
    )


def test_build_token_at_start_is_like_legacy():
    assert (
        build_category_pool_dir(MP, "cat-a", "{category}/templates")
        == f"{MP}/cat-a/templates"
    )


# --------------------------------------------------------------------------- #
# usage_subpath_matches  (reverse; ``relative`` = path after the mountpoint)
# --------------------------------------------------------------------------- #
def test_match_legacy_directory():
    assert usage_subpath_matches("cat-a/templates", "templates") is True


def test_match_legacy_file_path():
    assert usage_subpath_matches("cat-a/templates/abc.qcow2", "templates") is True


def test_match_legacy_multi_segment():
    assert usage_subpath_matches("cat-a/fast/templates", "fast/templates") is True


def test_match_token_directory():
    assert (
        usage_subpath_matches("fast/cat-a/templates", "fast/{category}/templates")
        is True
    )


def test_match_token_file_path():
    assert (
        usage_subpath_matches(
            "fast/cat-a/templates/abc.qcow2", "fast/{category}/templates"
        )
        is True
    )


def test_match_token_wrong_tier_is_false():
    assert (
        usage_subpath_matches("slow/cat-a/templates", "fast/{category}/templates")
        is False
    )


def test_match_token_category_is_single_segment():
    # {category} matches exactly one path segment, not several.
    assert (
        usage_subpath_matches("fast/a/b/templates", "fast/{category}/templates")
        is False
    )


def test_match_token_partial_leaf_is_false():
    # "templatesX" must not match the "templates" leaf.
    assert (
        usage_subpath_matches("fast/cat-a/templatesX", "fast/{category}/templates")
        is False
    )
