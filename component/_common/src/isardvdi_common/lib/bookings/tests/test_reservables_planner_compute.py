#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Edge-case unit tests for ``ReservablesPlannerCompute`` — the
interval-arithmetic and priority-resolution heart of the booking
subsystem.

These tests are a safety harness: they pin the current behaviour of the
priority-resolution and provisioning helpers so that future
refactors (batched DB queries, caching, restructured ReQL) can be
verified by re-running this suite. **None of the tests assume specific
DB call counts** — they assert on input → output equivalence so an
optimisation is free to change the call pattern as long as the result
is identical.

The tests here cover:

* ``payload_priority`` — single subitem, multiple subitems with same /
  different priority_id, missing priority_id, empty allowed lists,
  default-fallback path.
* ``user_matches_priority_rule`` — direction of the allowed-key search,
  empty list = match-all, role match, no match.
* ``most_restrictive_rule`` — accumulation across subitems.
* ``get_user_default_priority`` — fallback when no rule matches and
  no default rule is registered.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def compute_stub(monkeypatch):
    """Mock the rdb context for ``ReservablesPlannerCompute``.

    Tests parameterise the behaviour by overriding
    ``mock_table.side_effect`` to return a per-table fake.
    """
    from isardvdi_common.lib.bookings import reservables_planner_compute as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.ReservablesPlannerCompute,
        "_rdb_context",
        classmethod(lambda cls: _Ctx()),
    )
    monkeypatch.setattr(
        type(mod.ReservablesPlannerCompute),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    return {"mock_table": mock_table, "Cls": mod.ReservablesPlannerCompute}


def _make_payload(
    user_id="u-alice",
    role_id="user",
    category_id="default",
    group_id="default-default",
):
    return {
        "user_id": user_id,
        "role_id": role_id,
        "category_id": category_id,
        "group_id": group_id,
    }


def _make_rule(
    rule_id="default",
    priority=50,
    forbid_time=24,
    max_time=720,
    max_items=10,
    allowed=None,
):
    return {
        "id": f"{rule_id}-{priority}",
        "rule_id": rule_id,
        "priority": priority,
        "forbid_time": forbid_time,
        "max_time": max_time,
        "max_items": max_items,
        "allowed": allowed
        or {"users": [], "groups": [], "categories": [], "roles": []},
    }


class TestUserMatchesPriorityRule:
    """``user_matches_priority_rule`` is the linear-scan matcher used
    inside ``payload_priority``. It checks four allowed-keys in order
    (users → groups → categories → roles); inside each, scans rules
    looking for either an empty list (match-all) or the payload's id
    being in the list. First match wins.
    """

    def test_empty_users_allowed_matches_any_user(self, compute_stub):
        payload = _make_payload()
        rule = _make_rule(
            allowed={"users": [], "groups": [], "categories": [], "roles": []}
        )
        result = compute_stub["Cls"].user_matches_priority_rule(payload, [rule])
        assert result == rule

    def test_explicit_user_id_match(self, compute_stub):
        payload = _make_payload(user_id="u-alice")
        rule = _make_rule(
            allowed={
                "users": ["u-alice"],
                "groups": False,
                "categories": False,
                "roles": False,
            }
        )
        result = compute_stub["Cls"].user_matches_priority_rule(payload, [rule])
        assert result == rule

    def test_user_id_not_in_explicit_list_no_match(self, compute_stub):
        payload = _make_payload(user_id="u-alice")
        rule = _make_rule(
            allowed={
                "users": ["u-bob"],
                "groups": False,
                "categories": False,
                "roles": False,
            }
        )
        assert compute_stub["Cls"].user_matches_priority_rule(payload, [rule]) is False

    def test_role_match(self, compute_stub):
        payload = _make_payload(role_id="admin")
        # users/groups/categories all False; only roles matters
        rule = _make_rule(
            allowed={
                "users": False,
                "groups": False,
                "categories": False,
                "roles": ["admin"],
            }
        )
        result = compute_stub["Cls"].user_matches_priority_rule(payload, [rule])
        assert result == rule

    def test_users_take_precedence_over_role(self, compute_stub):
        """When a user-level rule and a role-level rule both could match,
        the user-level one wins because the loop iterates allowed-keys
        in fixed order and first match wins.
        """
        payload = _make_payload(user_id="u-alice", role_id="admin")
        user_rule = _make_rule(
            priority=99,
            allowed={
                "users": ["u-alice"],
                "groups": False,
                "categories": False,
                "roles": False,
            },
        )
        role_rule = _make_rule(
            priority=10,
            allowed={
                "users": False,
                "groups": False,
                "categories": False,
                "roles": ["admin"],
            },
        )
        # Order doesn't matter; the loop walks ALL rules per allowed-key.
        result = compute_stub["Cls"].user_matches_priority_rule(
            payload, [role_rule, user_rule]
        )
        assert result == user_rule

    def test_returns_false_when_no_rule_matches(self, compute_stub):
        payload = _make_payload(user_id="u-alice", role_id="user")
        rule = _make_rule(
            allowed={
                "users": ["u-bob"],
                "groups": ["other"],
                "categories": ["foo"],
                "roles": ["admin"],
            }
        )
        assert compute_stub["Cls"].user_matches_priority_rule(payload, [rule]) is False


class TestMostRestrictiveRule:
    """When a booking spans multiple subitems, priorities are
    accumulated by taking the per-subitem priority and the MIN of
    forbid_time / max_time / max_items across rules.
    """

    def test_first_subitem_seeds_state(self, compute_stub):
        new_priority = {
            "priority": 50,
            "forbid_time": 24,
            "max_time": 720,
            "max_items": 10,
        }
        result = compute_stub["Cls"].most_restrictive_rule(
            "subitem-a", new_priority, None
        )
        assert result == {
            "priority": {"subitem-a": 50},
            "forbid_time": 24,
            "max_time": 720,
            "max_items": 10,
        }

    def test_second_subitem_takes_min_of_each(self, compute_stub):
        first = compute_stub["Cls"].most_restrictive_rule(
            "subitem-a",
            {"priority": 50, "forbid_time": 24, "max_time": 720, "max_items": 10},
            None,
        )
        result = compute_stub["Cls"].most_restrictive_rule(
            "subitem-b",
            {"priority": 70, "forbid_time": 12, "max_time": 360, "max_items": 5},
            first,
        )
        assert result["priority"] == {"subitem-a": 50, "subitem-b": 70}
        assert result["forbid_time"] == 12  # min(24, 12)
        assert result["max_time"] == 360  # min(720, 360)
        assert result["max_items"] == 5  # min(10, 5)


class TestPayloadPriority:
    """End-to-end behaviour of the priority resolver. We mock the two
    rdb tables it touches (``reservables_<type>`` and
    ``bookings_priority``) and assert on the returned shape.
    """

    @pytest.fixture
    def priority_stub(self, compute_stub, monkeypatch):
        """Routes ``r.table(name)`` to per-table fakes whose ``.run()``
        returns the configured fixture data.
        """
        reservables_data = {}  # subitem_id -> reservable dict
        rules_by_rule_id = {}  # rule_id -> list of rule dicts (already sorted)

        def make_reservables_table():
            t = MagicMock(name="reservables_table")
            # Chain: r.table("reservables_X").get(subitem).run() -> reservables_data[subitem]
            t.get.side_effect = lambda subitem: MagicMock(
                run=MagicMock(return_value=reservables_data.get(subitem, {}))
            )
            return t

        def make_bookings_priority_table():
            t = MagicMock(name="bookings_priority_table")

            # r.table("bookings_priority").get_all(rule_id, index="rule_id")
            # .order_by(r.desc("priority")).run() -> rules
            def get_all_router(rule_id, index=None):
                m = MagicMock()
                m.order_by.return_value.run.return_value = rules_by_rule_id.get(
                    rule_id, []
                )
                return m

            t.get_all.side_effect = get_all_router
            return t

        def table_router(name):
            if name.startswith("reservables_"):
                return make_reservables_table()
            if name == "bookings_priority":
                return make_bookings_priority_table()
            return MagicMock(name=f"unmocked-{name}")

        compute_stub["mock_table"].side_effect = table_router

        # Stub r.desc — used inside .order_by(r.desc("priority"))
        from isardvdi_common.lib.bookings import reservables_planner_compute as mod

        monkeypatch.setattr(mod.r, "desc", lambda x: ("DESC", x))

        return {
            "reservables": reservables_data,
            "rules": rules_by_rule_id,
            "Cls": compute_stub["Cls"],
        }

    def test_single_subitem_with_explicit_priority_id(self, priority_stub):
        payload = _make_payload()
        priority_stub["reservables"]["NVIDIA-A40-1Q"] = {
            "id": "NVIDIA-A40-1Q",
            "priority_id": "high",
        }
        priority_stub["rules"]["high"] = [
            _make_rule(
                rule_id="high",
                priority=99,
                allowed={
                    "users": [],
                    "groups": False,
                    "categories": False,
                    "roles": False,
                },
            )
        ]

        result = priority_stub["Cls"].payload_priority(
            payload, {"vgpus": ["NVIDIA-A40-1Q"]}
        )
        assert result["priority"] == {"NVIDIA-A40-1Q": 99}
        assert result["forbid_time"] == 24
        assert result["max_time"] == 720
        assert result["max_items"] == 10

    def test_blank_priority_id_falls_back_to_default_rule(self, priority_stub):
        payload = _make_payload()
        priority_stub["reservables"]["NVIDIA-A40-1Q"] = {
            "id": "NVIDIA-A40-1Q",
            "priority_id": "",  # blank → default
        }
        priority_stub["rules"]["default"] = [
            _make_rule(
                rule_id="default",
                priority=10,
                allowed={
                    "users": [],
                    "groups": False,
                    "categories": False,
                    "roles": False,
                },
            )
        ]

        result = priority_stub["Cls"].payload_priority(
            payload, {"vgpus": ["NVIDIA-A40-1Q"]}
        )
        assert result["priority"] == {"NVIDIA-A40-1Q": 10}

    def test_missing_priority_id_falls_back_to_default(self, priority_stub):
        payload = _make_payload()
        priority_stub["reservables"]["NVIDIA-A40-1Q"] = {"id": "NVIDIA-A40-1Q"}
        priority_stub["rules"]["default"] = [
            _make_rule(
                rule_id="default",
                priority=10,
                allowed={
                    "users": [],
                    "groups": False,
                    "categories": False,
                    "roles": False,
                },
            )
        ]

        result = priority_stub["Cls"].payload_priority(
            payload, {"vgpus": ["NVIDIA-A40-1Q"]}
        )
        assert result["priority"] == {"NVIDIA-A40-1Q": 10}

    def test_no_matching_rule_returns_zero_priority(self, priority_stub):
        """When NO rule matches the payload (subitem's priority_id is
        registered but doesn't match, AND the ``default`` rule_id has
        no matching rule either), the function falls through to the
        ``get_user_default_priority`` no-match branch.

        Pinned shape after the default-fallback fix:
        ``get_user_default_priority`` returns ``priority`` as an int
        (matching the rule shape), so ``most_restrictive_rule`` wraps it
        once into ``{subitem: int}``. Pre-fix this was double-wrapped
        into ``{subitem: {subitem: int}}`` because the fallback returned
        a dict already; downstream callers comparing
        ``priority["priority"][subitem]`` as a numeric crashed on the
        nested shape.
        """
        payload = _make_payload(user_id="u-alice", role_id="user")
        priority_stub["reservables"]["NVIDIA-A40-1Q"] = {
            "id": "NVIDIA-A40-1Q",
            "priority_id": "restricted",
        }
        priority_stub["rules"]["restricted"] = [
            _make_rule(
                allowed={
                    "users": ["u-bob"],
                    "groups": False,
                    "categories": False,
                    "roles": False,
                }
            )
        ]
        # No "default" rule registered → the inner default-fallback also
        # finds no match and returns zeroed shape.
        priority_stub["rules"]["default"] = []

        result = priority_stub["Cls"].payload_priority(
            payload, {"vgpus": ["NVIDIA-A40-1Q"]}
        )
        assert result["priority"] == {"NVIDIA-A40-1Q": 0}
        assert result["forbid_time"] == 0
        assert result["max_time"] is None
        assert result["max_items"] is None

    def test_default_rule_match_returns_flat_priority(self, priority_stub):
        """Companion to the no-match case: when the subitem's specific
        priority_id has no matching rule but the ``default`` rule_id
        DOES match, the per-subitem priority value is the matched
        default rule's ``priority`` field. After the fix it is an int
        wrapped once by ``most_restrictive_rule`` into
        ``{subitem: int}`` — pre-fix it was a nested dict.
        """
        payload = _make_payload(user_id="u-alice", role_id="user")
        priority_stub["reservables"]["NVIDIA-A40-1Q"] = {
            "id": "NVIDIA-A40-1Q",
            "priority_id": "restricted",
        }
        # Subitem-specific rules don't match the user
        priority_stub["rules"]["restricted"] = [
            _make_rule(
                allowed={
                    "users": ["u-bob"],
                    "groups": False,
                    "categories": False,
                    "roles": False,
                }
            )
        ]
        # ...but a default rule DOES (empty users → match-all)
        priority_stub["rules"]["default"] = [
            _make_rule(
                rule_id="default",
                priority=15,
                forbid_time=24,
                max_time=720,
                max_items=10,
                allowed={
                    "users": [],
                    "groups": False,
                    "categories": False,
                    "roles": False,
                },
            )
        ]

        result = priority_stub["Cls"].payload_priority(
            payload, {"vgpus": ["NVIDIA-A40-1Q"]}
        )
        assert result["priority"] == {"NVIDIA-A40-1Q": 15}
        assert result["forbid_time"] == 24
        assert result["max_time"] == 720
        assert result["max_items"] == 10

    def test_multiple_subitems_same_priority_id(self, priority_stub):
        """Two subitems sharing one priority_id. Today the function
        re-fetches the rules per subitem; an optimisation that batches
        the lookup must produce the same per-subitem result.
        """
        payload = _make_payload()
        priority_stub["reservables"]["NVIDIA-A40-1Q"] = {"priority_id": "high"}
        priority_stub["reservables"]["NVIDIA-A40-2Q"] = {"priority_id": "high"}
        priority_stub["rules"]["high"] = [
            _make_rule(
                rule_id="high",
                priority=99,
                allowed={
                    "users": [],
                    "groups": False,
                    "categories": False,
                    "roles": False,
                },
            )
        ]

        result = priority_stub["Cls"].payload_priority(
            payload, {"vgpus": ["NVIDIA-A40-1Q", "NVIDIA-A40-2Q"]}
        )
        assert result["priority"] == {"NVIDIA-A40-1Q": 99, "NVIDIA-A40-2Q": 99}

    def test_multiple_subitems_different_priority_ids_min_aggregation(
        self, priority_stub
    ):
        """Subitem-a has rule (priority=99, forbid=24, max=720, items=10);
        subitem-b has rule (priority=50, forbid=12, max=360, items=5).
        The aggregate forbid_time/max_time/max_items take the MIN of
        each — pinning the ``most_restrictive_rule`` semantic.
        """
        payload = _make_payload()
        priority_stub["reservables"]["sub-a"] = {"priority_id": "high"}
        priority_stub["reservables"]["sub-b"] = {"priority_id": "low"}
        priority_stub["rules"]["high"] = [
            _make_rule(
                rule_id="high",
                priority=99,
                forbid_time=24,
                max_time=720,
                max_items=10,
                allowed={
                    "users": [],
                    "groups": False,
                    "categories": False,
                    "roles": False,
                },
            )
        ]
        priority_stub["rules"]["low"] = [
            _make_rule(
                rule_id="low",
                priority=50,
                forbid_time=12,
                max_time=360,
                max_items=5,
                allowed={
                    "users": [],
                    "groups": False,
                    "categories": False,
                    "roles": False,
                },
            )
        ]

        result = priority_stub["Cls"].payload_priority(
            payload, {"vgpus": ["sub-a", "sub-b"]}
        )
        assert result["priority"] == {"sub-a": 99, "sub-b": 50}
        assert result["forbid_time"] == 12
        assert result["max_time"] == 360
        assert result["max_items"] == 5

    def test_empty_subitem_list_raises_typeerror(self, priority_stub):
        """An empty reservables dict is a CALLER ERROR today — the
        function's loop doesn't iterate, so ``priority`` stays ``None``
        and ``priority["priority"] = items_priority`` crashes with
        ``TypeError: 'NoneType' object does not support item assignment``.

        This is a latent bug shape but it's pinned here so an
        optimisation that "tidies up" the empty case (e.g. returning
        ``{"priority": {}, ...}``) is a deliberate behaviour change,
        not a silent regression. Callers (``BookingsProcessed.add``,
        ``ReservablesPlannerProccess.existing_booking_update_fits``)
        always pass non-empty reservables — the empty path is not
        reachable from today's API.
        """
        payload = _make_payload()
        with pytest.raises(TypeError):
            priority_stub["Cls"].payload_priority(payload, {"vgpus": []})
