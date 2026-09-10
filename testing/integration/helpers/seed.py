#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""What the populate seed guarantees, for tests that pick fixtures by hand."""

from __future__ import annotations

# Seeded without a qcow2 on purpose (``isardvdi_testing.populate_test_db``
# → ``DISKLESS_STORAGE_IDS``), so a desktop derived from it wedges in
# CreatingDisk instead of reaching Stopped. e2e S4 needs that to reach a
# force_failable state; everything here has to steer around it, because the
# template listings are unordered and a blind ``[0]`` can land on it.
DISKLESS_TEMPLATE_ID = "template-s9-seed"


def derivable(templates: list) -> list:
    """The templates a desktop can actually be built from."""
    return [t for t in templates if t.id != DISKLESS_TEMPLATE_ID]
