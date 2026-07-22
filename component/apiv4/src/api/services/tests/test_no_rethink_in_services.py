# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin Tier 3.4 Batch 5 — services must not import or use rethinkdb.

Every direct DB call from ``api/services/**.py`` was migrated into
``isardvdi_common.lib.<feature>.<Feature>Processed`` across Tier 3.4
Batches 0-4 (35 commits). This test prevents regrowth: any new
``r.table(...)`` / ``RethinkSharedConnection._rdb_*`` /
``from rethinkdb import r`` in ``api/services/**.py`` will fail CI
the same day it lands.

If a future migration legitimately needs to bypass ``_common``
(should be rare — see the isardvdi-common skill), add the file to
``ALLOWLIST`` with a one-line rationale.
"""

import re
from pathlib import Path

# Filenames whose direct rdb usage is consciously allowed. Empty
# today; every entry must carry a rationale comment so the next
# reviewer can challenge it.
ALLOWLIST: set[str] = set()

_SERVICES_ROOT = Path(__file__).resolve().parent.parent

# Each pattern is matched against every line; comments and string
# literals also count, so the post-Tier-3.4 service tree must not
# carry even doc-comment references like ``# r.table(...)`` to
# avoid false-negative pins.
_BANNED_PATTERNS = (
    re.compile(r"\br\.table\("),
    re.compile(r"RethinkSharedConnection\._rdb_"),
    re.compile(r"from\s+rethinkdb\s+import"),
    re.compile(r"\bimport\s+rethinkdb\b"),
)


def _python_sources() -> list[Path]:
    """Return every ``.py`` file under ``api/services/`` excluding tests."""
    out: list[Path] = []
    for path in _SERVICES_ROOT.rglob("*.py"):
        rel = path.relative_to(_SERVICES_ROOT)
        # Don't lint the contract test itself or its sibling tests/.
        if rel.parts and rel.parts[0] == "tests":
            continue
        if path.name == "__init__.py":
            continue
        out.append(path)
    return sorted(out)


def test_no_rethink_in_services() -> None:
    """No direct rethinkdb calls in ``api/services/**.py``."""
    offenders: list[str] = []
    for path in _python_sources():
        rel = str(path.relative_to(_SERVICES_ROOT))
        if rel in ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for pattern in _BANNED_PATTERNS:
                if pattern.search(line):
                    offenders.append(f"  {rel}:{line_no}: {line.strip()}")
                    break
    assert not offenders, (
        "Tier 3.4 Batch 5 contract: services must delegate every DB "
        "call through isardvdi_common.lib.<Feature>Processed. The "
        "following lines reintroduce direct rethinkdb usage in "
        "api/services/ and need to migrate (or be added to "
        "ALLOWLIST with a rationale):\n" + "\n".join(offenders)
    )


def test_services_root_is_present() -> None:
    """Sanity: catch typos in _SERVICES_ROOT.

    ``services/`` is a namespace package (no ``__init__.py``) — pytest
    auto-discovers under the ``api`` package root, so the file walk
    must still find concrete service modules even without an init.
    """
    assert _SERVICES_ROOT.is_dir(), _SERVICES_ROOT
    assert _SERVICES_ROOT.name == "services"


def test_python_sources_finds_real_files() -> None:
    """Sanity: the walk picks up non-test service modules."""
    rels = {str(p.relative_to(_SERVICES_ROOT)) for p in _python_sources()}
    # At least one well-known service file must be in the walk.
    assert any(r.endswith("admin/stats.py") for r in rels), sorted(rels)[:5]
