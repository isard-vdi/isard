#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pure helpers for building and matching *category* storage-pool paths.

A category pool stores a disk at ``<mountpoint>/<category>/<usage_subpath>``.
An admin may instead put a ``{category}`` placeholder inside the usage subpath
to choose where the per-category segment lands -- e.g. ``fast/{category}/templates``
yields ``<mountpoint>/fast/<category>/templates`` so a single tier disk mounted
once at ``<mountpoint>/fast`` serves every category. Without the token the
category is inserted right after the mountpoint, exactly as before (backward
compatible).

These helpers only concern *category* pools. The default pool has no category
segment and does not use the token.
"""

import re

CATEGORY_TOKEN = "{category}"


def build_category_pool_dir(mountpoint, category_id, usage_subpath):
    """Build the on-disk directory for a category pool.

    If ``usage_subpath`` contains the ``{category}`` token the admin controls the
    category position: substitute the token and do NOT auto-insert the category.
    Otherwise keep the backward-compatible ``<mountpoint>/<category>/<subpath>``.
    """
    if CATEGORY_TOKEN in usage_subpath:
        return f"{mountpoint}/{usage_subpath.replace(CATEGORY_TOKEN, category_id)}"
    return f"{mountpoint}/{category_id}/{usage_subpath}"


def usage_subpath_matches(relative, usage_subpath):
    """Whether ``relative`` was produced by ``usage_subpath`` for some category.

    ``relative`` is a disk path with the pool mountpoint already stripped (and no
    leading slash). Token subpaths match with ``{category}`` standing for exactly
    one path segment; legacy subpaths have the category as the leading segment,
    which is stripped before comparing (mirrors the historical behaviour).
    """
    if CATEGORY_TOKEN in usage_subpath:
        pattern = (
            "^"
            + "/".join(
                "[^/]+" if segment == CATEGORY_TOKEN else re.escape(segment)
                for segment in usage_subpath.split("/")
            )
            + r"(/|$)"
        )
        return re.match(pattern, relative) is not None
    rest = relative.split("/", 1)
    rest = rest[1] if len(rest) > 1 else ""
    return rest == usage_subpath or rest.startswith(usage_subpath + "/")
