# SPDX-License-Identifier: AGPL-3.0-or-later

"""A reason is only readable back if both sides spell it the same way.

``lane_shed_decision`` produces a reason; the health read, the no-consumer gate
and the 429 read it back. While both sides were string literals, a rename at the
producer left a consumer comparing against a value nothing emits — and that
failure is silent, because the flag it feeds simply stays False.

The regression itself is pinned next door in ``test_queue_coverage.py``. What
lives here is the guard: it fails on the rename rather than on the symptom, so
the next one is caught at the point it is made.
"""

import ast
import inspect

import pytest
from isardvdi_common.lib import queue_coverage as qc


def _reason_comparison_literals():
    """Every string this module compares a decision reason against."""
    tree = ast.parse(inspect.getsource(qc))
    found = []

    def reads_a_reason(node):
        if isinstance(node, ast.Subscript):
            return isinstance(node.slice, ast.Constant) and node.slice.value == "reason"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            return (
                node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "reason"
            )
        return isinstance(node, ast.Name) and node.id == "reason"

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or not reads_a_reason(node.left):
            continue
        for comparator in node.comparators:
            parts = (
                comparator.elts
                if isinstance(comparator, (ast.Tuple, ast.List, ast.Set))
                else [comparator]
            )
            found += [p.value for p in parts if isinstance(p, ast.Constant)]
    return found


def test_no_consumer_compares_against_a_reason_nothing_emits():
    """The guard the rename walked past.

    A literal here is not wrong in itself — it is wrong when it is not a value
    the producer can return, which is unreadable at the call site and invisible
    at runtime.
    """
    stray = [r for r in _reason_comparison_literals() if r not in qc.DECISION_REASONS]
    assert stray == [], (
        f"compared against {stray}, which lane_shed_decision never returns; "
        f"the vocabulary is {sorted(qc.DECISION_REASONS)}"
    )


@pytest.mark.parametrize("reason", sorted(qc.BLIND_REASONS))
def test_a_blind_reason_is_part_of_the_vocabulary(reason):
    assert reason in qc.DECISION_REASONS
