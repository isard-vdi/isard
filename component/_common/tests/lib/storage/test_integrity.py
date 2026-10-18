# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integrity detection levels: each returns findings and touches nothing."""

from isardvdi_common.lib.storage.integrity import (
    detect_broken_chain,
    detect_coherence,
    detect_missing_file,
    detect_on_disk_dependents,
)

BASE = "11111111-1111-1111-1111-111111111111"
CHILD = "22222222-2222-2222-2222-222222222222"
GRAND = "33333333-3333-3333-3333-333333333333"
OTHER = "99999999-9999-9999-9999-999999999999"


def _p(uuid):
    return f"/pool/{uuid}.qcow2"


def _entry(uuid, backing=None, readable=True):
    return {
        "uuid": uuid,
        "size": 10,
        "readable": readable,
        "backing_raw": _p(backing) if backing else None,
        "backing_uuid": backing if backing else None,
    }


# --- L0 coherence ----------------------------------------------------------


def test_l0_flags_a_row_whose_owner_is_gone():
    findings = detect_coherence(
        [{"id": "s1", "status": "ready", "user_id": "ghost"}],
        live_user_ids={"alice"},
        storages_used_by_live_domains=set(),
    )
    assert len(findings) == 1
    sid, action, detail = findings[0]
    assert (sid, action) == ("s1", "review_coherence")
    assert any("ghost" in r for r in detail["reasons"])


def test_l0_flags_a_gone_disk_a_live_desktop_still_uses():
    findings = detect_coherence(
        [{"id": "s1", "status": "deleted", "user_id": "alice"}],
        live_user_ids={"alice"},
        storages_used_by_live_domains={"s1"},
    )
    assert findings[0][1] == "review_coherence"
    assert any("live desktop" in r for r in findings[0][2]["reasons"])


def test_l0_leaves_a_healthy_row_alone():
    findings = detect_coherence(
        [{"id": "s1", "status": "ready", "user_id": "alice"}],
        live_user_ids={"alice"},
        storages_used_by_live_domains={"s1"},
    )
    assert findings == []


def test_l0_does_not_flag_a_gone_disk_nobody_uses():
    findings = detect_coherence(
        [{"id": "s1", "status": "deleted", "user_id": "alice"}],
        live_user_ids={"alice"},
        storages_used_by_live_domains=set(),
    )
    assert findings == []


# --- L1 missing file -------------------------------------------------------


def test_l1_flags_a_live_row_whose_file_is_absent():
    findings = detect_missing_file(
        [{"id": "s1", "status": "ready", "path": _p(CHILD)}], {}
    )
    assert findings[0][0] == "s1"
    assert findings[0][1] == "review_coherence"


def test_l1_leaves_a_live_row_whose_file_is_present():
    index = {_p(CHILD): _entry(CHILD)}
    findings = detect_missing_file(
        [{"id": "s1", "status": "ready", "path": _p(CHILD)}], index
    )
    assert findings == []


def test_l1_does_not_chase_a_gone_row():
    findings = detect_missing_file(
        [{"id": "s1", "status": "deleted", "path": _p(CHILD)}], {}
    )
    assert findings == []


# --- L2 broken chain -------------------------------------------------------


def test_l2_flags_a_moved_parent_as_rebase_backing():
    index = {_p(CHILD): _entry(CHILD, backing=BASE)}  # BASE itself absent
    findings = detect_broken_chain([{"id": "s1", "path": _p(CHILD)}], index)
    assert findings == [
        (
            "s1",
            "rebase_backing",
            {"reason": "backing file not found in any pool", "backing": _p(BASE)},
        )
    ]


def test_l2_leaves_a_resolvable_chain_alone():
    index = {_p(CHILD): _entry(CHILD, backing=BASE), _p(BASE): _entry(BASE)}
    findings = detect_broken_chain([{"id": "s1", "path": _p(CHILD)}], index)
    assert findings == []


def test_l2_flags_an_unresolvable_reference_as_review_coherence():
    entry = {
        "uuid": CHILD,
        "size": 10,
        "readable": True,
        "backing_raw": "/weird/no-uuid.img",
        "backing_uuid": None,
    }
    index = {_p(CHILD): entry}
    findings = detect_broken_chain([{"id": "s1", "path": _p(CHILD)}], index)
    assert findings[0][1] == "review_coherence"


def test_l2_leaves_a_base_with_no_backing_alone():
    index = {_p(BASE): _entry(BASE)}
    findings = detect_broken_chain([{"id": "s1", "path": _p(BASE)}], index)
    assert findings == []


# --- L3 on-disk dependents -------------------------------------------------


def test_l3_flags_a_gone_base_a_live_child_backs_onto():
    index = {_p(CHILD): _entry(CHILD, backing=BASE)}
    findings = detect_on_disk_dependents(
        [("s-base", _p(BASE))], index, live_uuids={CHILD}
    )
    assert findings == [
        (
            "s-base",
            "review_dependents",
            {"path": _p(BASE), "dependents": [_p(CHILD)], "unreadable": []},
        )
    ]


def test_l3_ignores_a_child_that_is_itself_not_live():
    index = {_p(CHILD): _entry(CHILD, backing=BASE)}
    findings = detect_on_disk_dependents(
        [("s-base", _p(BASE))], index, live_uuids=set()
    )
    assert findings == []


def test_l3_follows_the_chain_to_a_live_grandchild_through_a_dead_intermediate():
    index = {
        _p(CHILD): _entry(CHILD, backing=BASE),
        _p(GRAND): _entry(GRAND, backing=CHILD),
    }
    findings = detect_on_disk_dependents(
        [("s-base", _p(BASE))], index, live_uuids={GRAND}
    )
    assert findings[0][2]["dependents"] == [_p(GRAND)]


def test_l3_does_not_flag_when_nothing_backs_onto_the_base():
    index = {_p(CHILD): _entry(CHILD, backing=OTHER)}
    findings = detect_on_disk_dependents(
        [("s-base", _p(BASE))], index, live_uuids={CHILD}
    )
    assert findings == []


def test_l3_does_not_invent_a_dependent_from_an_unreadable_candidate():
    """An unreadable file cannot be confirmed to back onto the base, so it is
    never reported as a dependent (the purge guard fails closed separately)."""
    index = {_p(CHILD): _entry(CHILD, backing=None, readable=False)}
    findings = detect_on_disk_dependents(
        [("s-base", _p(BASE))], index, live_uuids={CHILD}
    )
    assert findings == []
