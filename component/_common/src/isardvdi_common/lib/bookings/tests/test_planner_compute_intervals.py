"""Unit tests for the pure interval-algebra helpers in
``api_reservables_planner_compute``.

These functions are the load-bearing math behind GPU booking availability: a
desktop that needs SEVERAL cards is bookable only where ALL its profiles overlap
(``intersect_different_subitem_plan``), the SAME profile across several cards sums
its units (``intersect_same_subitem_plan``), and adjacent free windows collapse
into one (``join_consecutive_plans``).

The module cannot be imported bare (``from api import app`` boots Flask + a
RethinkDB connection at import time), so — mirroring ``api_reservables_test.py``
and ``api_hypervisors_gpu_model_test.py`` — we extract ONLY these self-contained
functions (plus the ``_sorted_atomic_items`` helper) from the source via ``ast``
and exec them with ``portion`` injected. They touch no DB. Times are plain ints.
"""

import ast
import os

import portion

_SRC = os.path.join(os.path.dirname(__file__), "../reservables_planner_compute.py")
_WANTED = {
    "_sorted_atomic_items",
    "intersect_same_subitem_plan",
    "intersect_different_subitem_plan",
    "join_consecutive_plans",
}


def _load():
    """On this branch the interval helpers are classmethods of
    ``ReservablesPlannerCompute`` (upstream has them module-level), so the
    extractor walks into the class body, strips the ``cls`` parameter and the
    ``cls.``-qualified self-calls, and execs the result module-level."""
    src_text = open(_SRC).read()
    tree = ast.parse(src_text)
    funcs = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in _WANTED
    ]
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            funcs += [
                n
                for n in node.body
                if isinstance(n, ast.FunctionDef) and n.name in _WANTED
            ]
    assert {f.name for f in funcs} == _WANTED, "could not locate all target functions"
    import textwrap

    pieces = []
    for f in funcs:
        seg = textwrap.dedent(ast.get_source_segment(src_text, f))
        seg = seg.replace("(\n        cls,", "(").replace("(cls, ", "(")
        seg = seg.replace("(cls)", "()").replace("cls.", "")
        pieces.append(seg)
    ns = {"P": portion}
    exec(compile("\n\n".join(pieces), _SRC, "exec"), ns)
    return ns


_H = _load()


def _seg(start, end, units, id, subitem=None):
    s = {"start": start, "end": end, "units": units, "id": id}
    if subitem is not None:
        s["subitem"] = subitem
    return s


# --- intersect_different_subitem_plan (the multi-card AND) -------------------
# A two-GPU desktop is bookable only where BOTH profiles overlap.


def _diff(segs, expected):
    return _H["intersect_different_subitem_plan"](segs, expected_subitems=expected)


def test_two_cards_interleaved_yields_the_intersection():
    # X planned [0,6], Y planned [3,9]  ->  bookable only [3,6]
    out = _diff([_seg(0, 6, 1, "cx", "X"), _seg(3, 9, 1, "cy", "Y")], expected=2)
    assert len(out) == 1
    assert (out[0]["start"], out[0]["end"]) == (3, 6)


def test_two_cards_full_overlap_is_the_whole_window():
    out = _diff([_seg(0, 10, 1, "cx", "X"), _seg(0, 10, 1, "cy", "Y")], expected=2)
    assert [(w["start"], w["end"]) for w in out] == [(0, 10)]


def test_two_cards_nested_yields_inner():
    out = _diff([_seg(0, 10, 1, "cx", "X"), _seg(3, 6, 1, "cy", "Y")], expected=2)
    assert [(w["start"], w["end"]) for w in out] == [(3, 6)]


def test_two_cards_disjoint_is_empty():
    out = _diff([_seg(0, 3, 1, "cx", "X"), _seg(6, 9, 1, "cy", "Y")], expected=2)
    assert out == []


def test_one_card_only_is_empty_when_two_expected():
    # Only X is planned; the desktop needs X AND Y -> nothing bookable.
    out = _diff([_seg(0, 6, 1, "cx", "X")], expected=2)
    assert out == []


def test_three_cards_all_must_overlap():
    out = _diff(
        [
            _seg(0, 9, 1, "cx", "X"),
            _seg(3, 9, 1, "cy", "Y"),
            _seg(5, 9, 1, "cz", "Z"),
        ],
        expected=3,
    )
    assert [(w["start"], w["end"]) for w in out] == [(5, 9)]


def test_units_is_the_min_across_profiles():
    # X offers 4 units, Y offers 2 in the overlap -> min == 2.
    out = _diff([_seg(0, 6, 4, "cx", "X"), _seg(3, 9, 2, "cy", "Y")], expected=2)
    assert len(out) == 1
    assert out[0]["units"] == 2


def test_touching_boundary_yields_only_a_degenerate_point():
    # Closed intervals [0,6] and [6,9] meet only at the single point 6: the
    # function returns a zero-length window there (documented quirk; a real
    # booking can't fit a 0-length window, so it is harmless in practice).
    out = _diff([_seg(0, 6, 1, "cx", "X"), _seg(6, 9, 1, "cy", "Y")], expected=2)
    assert [(w["start"], w["end"]) for w in out] == [(6, 6)]


# --- intersect_same_subitem_plan (same profile across cards, units SUM) ------


def test_same_profile_two_cards_overlap_sums_units():
    # Same reservable on two cards, overlapping [3,6] -> 1+1 = 2 units there.
    out = _H["intersect_same_subitem_plan"](
        [_seg(0, 6, 1, "card1"), _seg(3, 9, 1, "card2")], "RES"
    )
    overlap = [w for w in out if w["start"] == 3 and w["end"] == 6]
    assert overlap and overlap[0]["units"] == 2
    assert set(overlap[0]["ids"]) == {"card1", "card2"}


def test_same_profile_non_overlapping_kept_separate():
    out = _H["intersect_same_subitem_plan"](
        [_seg(0, 3, 1, "card1"), _seg(6, 9, 1, "card2")], "RES"
    )
    assert sorted((w["start"], w["end"], w["units"]) for w in out) == [
        (0, 3, 1),
        (6, 9, 1),
    ]


def test_same_profile_three_cards_full_overlap_sums_to_three():
    out = _H["intersect_same_subitem_plan"](
        [_seg(0, 9, 1, "c1"), _seg(0, 9, 1, "c2"), _seg(0, 9, 1, "c3")], "RES"
    )
    assert len(out) == 1 and out[0]["units"] == 3


# --- join_consecutive_plans -------------------------------------------------
# NOTE: this helper skips any segment failing ``if interval.get("start")`` —
# i.e. a falsy start. In production ``start`` is always a tz-aware datetime
# (truthy), so the tests use non-zero times; a literal 0 would be dropped.


def test_adjacent_windows_merge_into_one_available():
    # closedopen [10,13)+[13,16) are contiguous -> a single [10,16) window.
    out = _H["join_consecutive_plans"]([_seg(10, 13, 1, "a"), _seg(13, 16, 1, "a")])
    assert [(w["start"], w["end"]) for w in out] == [(10, 16)]
    assert out[0]["units"] == "Enough"


def test_gapped_windows_stay_separate():
    out = _H["join_consecutive_plans"]([_seg(10, 13, 1, "a"), _seg(14, 16, 1, "a")])
    assert [(w["start"], w["end"]) for w in out] == [(10, 13), (14, 16)]


def test_zero_unit_windows_keep_event_type():
    """Upstream drops zero-unit windows here; this branch's twin diverged
    deliberately — it preserves the event_type lane (available / overridable /
    unavailable) and marks unavailable windows with units=-1 so the frontend
    calendar can paint them. Pin the branch contract instead."""
    seg = _seg(10, 16, 0, "a")
    seg["event_type"] = "unavailable"
    out = _H["join_consecutive_plans"]([seg])
    assert len(out) == 1
    assert out[0]["units"] == -1
