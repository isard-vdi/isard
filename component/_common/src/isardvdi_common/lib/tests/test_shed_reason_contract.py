#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The counters must be able to name every reason the gate sheds for.

``governor_counters`` keeps a closed set of reasons and files anything else
under ``other``. That guard exists to stop an arbitrary string turning the
totals hash into an unbounded key space -- it was never meant to swallow a
reason the gate genuinely produces. When it does, the count is still right but
the label is wrong, and the alert built on that label goes on to name causes
that are not the one that fired.

The set cannot simply be imported: ``queue_coverage`` imports
``governor_counters`` to record its own sheds, so the arrow points one way only.
This is what keeps the spelled-out copy honest, and it is written to notice a
reason added later rather than to restate today's three.
"""

import ast
import inspect

from isardvdi_common.lib import governor_counters, queue_coverage


def _reject_reasons():
    """Every ``reason`` the gate can return alongside a ``reject`` decision.

    Read out of the source rather than listed here, so a fourth reason added to
    the gate shows up as a failure instead of quietly becoming ``other``.
    """
    tree = ast.parse(inspect.getsource(queue_coverage))
    constants = {
        node.targets[0].id: node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }

    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Tuple):
            continue
        head = node.value.elts[0] if node.value.elts else None
        if not (isinstance(head, ast.Constant) and head.value == "reject"):
            continue
        for sub in ast.walk(node.value):
            if not isinstance(sub, ast.Dict):
                continue
            for key, value in zip(sub.keys, sub.values):
                if not (isinstance(key, ast.Constant) and key.value == "reason"):
                    continue
                if isinstance(value, ast.Constant):
                    found.add(value.value)
                elif isinstance(value, ast.Name) and value.id in constants:
                    found.add(constants[value.id])
    return found


def test_the_reader_found_the_reject_paths_at_all():
    """Guard the guard: an empty scan would make the contract below vacuous."""
    assert len(_reject_reasons()) >= 3


def test_every_reason_the_gate_rejects_with_can_be_counted():
    shed_reasons = governor_counters._REASONS[governor_counters.SHED]
    missing = _reject_reasons() - shed_reasons
    assert not missing, (
        f"{sorted(missing)} would be filed as "
        f"'{governor_counters._OTHER_REASON}', so the alert names a cause that "
        f"did not fire"
    )


def test_the_counters_claim_no_reason_the_gate_cannot_produce():
    """The other direction: a stale entry here is a label nothing will ever set."""
    shed_reasons = governor_counters._REASONS[governor_counters.SHED]
    assert not shed_reasons - queue_coverage.DECISION_REASONS


def test_a_blind_shed_keeps_its_own_name():
    """The case that was collapsing: ignorance must not read as a dead lane."""
    for reason in queue_coverage.BLIND_REASONS:
        assert (
            governor_counters._reason(governor_counters.SHED, reason) == reason
        ), "a fleet the governor cannot read is not the same as one with no worker"


def test_an_arbitrary_string_still_collapses():
    """The guard the closed set was actually for is untouched."""
    assert (
        governor_counters._reason(governor_counters.SHED, "whatever-someone-passes")
        == governor_counters._OTHER_REASON
    )
