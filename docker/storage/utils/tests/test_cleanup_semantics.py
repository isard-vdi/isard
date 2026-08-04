"""Two decisions the cleanup makes badly on a real estate.

**The orphan guard has no way out.** It aborts when more than 80% of the files
on disk have no database row, on the theory that the API must be lying. That is
right by default, and it fired correctly on a rebuilt database over an old
filesystem. But there is no way for an operator who has *checked* to proceed:
the tool is simply unusable on an estate that genuinely is mostly orphans, which
is exactly the estate that needs it.

**Discarded copies are stranded, not swept.** A soft-deleted disk keeps its
backing reference. When the parent is removed, that copy can never be restored
into anything — it is dead weight the cleanup leaves behind. Measured on a live
share after a real ``cleanup --move``: 364 files moved, no chain broken, and
**23 recycle-bin copies left pointing at a parent that was gone**.
"""

import sys
from pathlib import Path

_UTILS = Path(__file__).resolve().parents[1]
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

import pytest  # noqa: E402
from isardvdi_common.lib.storage.paths import RECYCLE_BIN_DIR  # noqa: E402

pytest.importorskip(
    "isardvdi_apiv4_client.client",
    reason="the generated apiv4 client is produced by codegen",
)

import importlib.util  # noqa: E402
from importlib.machinery import SourceFileLoader  # noqa: E402


def _load_cli():
    loader = SourceFileLoader("storagecli", str(_UTILS / "storage"))
    spec = importlib.util.spec_from_loader("storagecli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


cli = _load_cli()


# ── the orphan guard ──────────────────────────────────────────────────────


def test_the_guard_still_refuses_by_default():
    """The default must not change: a suspicious ratio stops the run."""
    assert cli._orphan_ratio_refused(orphans=743, total=793, db_rows=56, accepted=False)


def test_a_ratio_below_the_threshold_is_never_refused():
    assert not cli._orphan_ratio_refused(
        orphans=437, total=793, db_rows=356, accepted=False
    )


def test_a_small_estate_is_never_refused_however_lopsided():
    """Ten files with no rows is a fresh install, not a broken API."""
    assert not cli._orphan_ratio_refused(
        orphans=10, total=10, db_rows=0, accepted=False
    )


def test_an_operator_who_has_checked_may_proceed():
    """The escape hatch: same numbers, acknowledged."""
    assert not cli._orphan_ratio_refused(
        orphans=743, total=793, db_rows=56, accepted=True
    )


# ── the recycle-bin cascade ───────────────────────────────────────────────


def _deps(dependency_map):
    reverse = {}
    for child, parent in dependency_map.items():
        if parent:
            reverse.setdefault(parent, []).append(child)
    return {"dependency_map": dependency_map, "reverse_map": reverse}


def test_a_bin_copy_of_a_disk_being_removed_goes_with_it():
    parent = "/isard/groups/parent.qcow2"
    binned = f"/isard/groups/{RECYCLE_BIN_DIR}/child.qcow2"
    deps = _deps({parent: None, binned: parent})

    out = cli._with_stranded_bin_copies({parent}, deps)

    assert binned in out, (
        "the discarded copy still points at a parent that is going away; left "
        "behind it can never be restored into anything"
    )


def test_a_bin_copy_whose_parent_survives_is_kept():
    """That is a restorable backup, not dead weight."""
    parent = "/isard/groups/parent.qcow2"
    binned = f"/isard/groups/{RECYCLE_BIN_DIR}/child.qcow2"
    deps = _deps({parent: None, binned: parent})

    assert binned not in cli._with_stranded_bin_copies(set(), deps)


def test_a_live_disk_is_never_dragged_in():
    """A live child of a removed parent should not exist in the first place.

    ``set_maintenance`` refuses any op on a disk that has children, so this is
    an incoherence rather than a case to handle. The cascade leaves it alone so
    the evidence survives for whoever has to explain it.
    """
    parent = "/isard/groups/parent.qcow2"
    live_child = "/isard/groups/child.qcow2"
    deps = _deps({parent: None, live_child: parent})

    assert live_child not in cli._with_stranded_bin_copies({parent}, deps)


def test_the_cascade_reaches_a_bin_copy_behind_another():
    parent = "/isard/templates/tpl.qcow2"
    b1 = f"/isard/templates/{RECYCLE_BIN_DIR}/mid.qcow2"
    b2 = f"/isard/groups/{RECYCLE_BIN_DIR}/leaf.qcow2"
    deps = _deps({parent: None, b1: parent, b2: b1})

    out = cli._with_stranded_bin_copies({parent}, deps)

    assert b1 in out and b2 in out, "the cascade stopped at the first level"


def test_a_bin_copy_whose_parent_is_already_gone_is_swept():
    """Nothing is being deleted here; the parent simply is not on disk."""
    binned = f"/isard/groups/{RECYCLE_BIN_DIR}/orphan.qcow2"
    deps = _deps({binned: "/isard/templates/vanished.qcow2"})

    assert binned in cli._with_stranded_bin_copies(set(), deps)
