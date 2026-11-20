#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""How many temporal desktops a user may hold per template.

Several are allowed only on ``FRONTEND_MODE=actual``; anywhere the old frontend
is still reachable the v3 get-or-create stays, since it maps each template card
to a single desktop, and a submitted configuration is refused rather than
reused away.
"""

from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers import rules
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops_nonpersistent as mod

DNP = mod.DesktopsNonpersistentProcessed


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setenv("FRONTEND_MODE", "actual")
    # No rule applies, so the mode comes from FRONTEND_MODE.
    monkeypatch.setattr(rules, "_get_applied_frontend_mode_rule", lambda payload: None)
    monkeypatch.setattr(DNP, "_rdb_context", classmethod(lambda cls: nullcontext()))
    # Metaclass property: patching it on DNP itself can't be undone on teardown.
    monkeypatch.setattr(type(DNP), "_rdb_connection", property(lambda cls: None))

    rethink = MagicMock()
    rethink.table.return_value.get.return_value.run.return_value = {"id": "u-1"}
    monkeypatch.setattr(mod, "r", rethink)

    created = []

    def fake_create(
        cls,
        user_id,
        template_id,
        name=None,
        description=None,
        new_data=None,
        image=None,
        booking_end=None,
        reservables=None,
    ):
        created.append((user_id, template_id, name, description, new_data, image))
        return f"d-{len(created)}"

    monkeypatch.setattr(
        DNP, "_nonpersistent_desktop_create_and_start", classmethod(fake_create)
    )
    monkeypatch.setattr(mod.DesktopEvents, "desktop_start", staticmethod(MagicMock()))
    monkeypatch.setattr(
        mod.HypervisorsProcessed,
        "check_virt_storage_pool_availability",
        staticmethod(MagicMock()),
    )
    monkeypatch.setattr(
        mod.Scheduler, "add_desktop_timeouts", staticmethod(MagicMock())
    )
    monkeypatch.setattr(
        mod.Helpers, "gen_payload_from_user", staticmethod(lambda user: {})
    )
    bulk_delete = MagicMock()
    monkeypatch.setattr(
        mod.DesktopNonpersistentEvents,
        "desktops_non_persistent_delete",
        staticmethod(bulk_delete),
    )
    return {"rethink": rethink, "created": created, "bulk_delete": bulk_delete}


def _existing(stub, *desktops):
    """Stub the (user, template) lookup the one-slot path does."""
    query = stub["rethink"].db.return_value.table.return_value.get_all.return_value
    query.filter.return_value.pluck.return_value.run.return_value = list(desktops)


def test_same_template_twice_creates_two_desktops(stub):
    first = DNP.new_desktop("u-1", "t-1")
    second = DNP.new_desktop("u-1", "t-1")

    assert [first, second] == ["d-1", "d-2"]
    assert stub["created"] == [("u-1", "t-1", None, None, None, None)] * 2


def test_returns_bare_id_and_forwards_name(stub):
    desktop_id = DNP.new_desktop("u-1", "t-1", name="mine", description="d")

    assert desktop_id == "d-1"
    assert stub["created"] == [("u-1", "t-1", "mine", "d", None, None)]


# ``all`` and ``hidden`` also keep the old frontend reachable.
@pytest.mark.parametrize("mode", ["deprecated", "all", "hidden", "bogus"])
def test_old_frontend_reachable_reuses_the_existing_desktop(monkeypatch, stub, mode):
    monkeypatch.setenv("FRONTEND_MODE", mode)
    _existing(stub, {"id": "d-old", "status": "Stopped"})

    assert DNP.new_desktop("u-1", "t-1") == "d-old"
    assert stub["created"] == []
    # No wait_seconds: wait_status polls every 2s and would 500 first.
    mod.DesktopEvents.desktop_start.assert_called_once_with("d-old")


@pytest.mark.parametrize("mode", ["deprecated", "all", "hidden"])
def test_a_submitted_configuration_is_refused_when_the_slot_is_taken(
    monkeypatch, stub, mode
):
    monkeypatch.setenv("FRONTEND_MODE", mode)
    _existing(stub, {"id": "d-old", "status": "Stopped"})

    with pytest.raises(Error) as refused:
        DNP.new_desktop(
            "u-1",
            "t-1",
            name="mine",
            new_data={"hardware": {"vcpus": 4}},
            allow_reuse=False,
        )

    assert refused.value.error["error"] == "conflict"
    assert refused.value.error["description_code"] == "single_temporal_per_template"
    assert stub["created"] == []
    mod.DesktopEvents.desktop_start.assert_not_called()


def test_a_submitted_configuration_creates_when_the_slot_is_free(monkeypatch, stub):
    monkeypatch.setenv("FRONTEND_MODE", "all")
    _existing(stub)

    desktop_id = DNP.new_desktop(
        "u-1",
        "t-1",
        name="mine",
        new_data={"hardware": {"vcpus": 4}},
        allow_reuse=False,
    )

    assert desktop_id == "d-1"
    assert stub["created"] == [
        ("u-1", "t-1", "mine", None, {"hardware": {"vcpus": 4}}, None)
    ]


def test_old_frontend_reachable_creates_when_none_exists(monkeypatch, stub):
    monkeypatch.setenv("FRONTEND_MODE", "deprecated")
    _existing(stub)

    assert DNP.new_desktop("u-1", "t-1") == "d-1"
    assert stub["created"] == [("u-1", "t-1", None, None, None, None)]
    stub["bulk_delete"].assert_not_called()


def test_old_frontend_reachable_collapses_leftovers(monkeypatch, stub):
    monkeypatch.setenv("FRONTEND_MODE", "deprecated")
    _existing(
        stub, {"id": "d-a", "status": "Started"}, {"id": "d-b", "status": "Started"}
    )

    assert DNP.new_desktop("u-1", "t-1") == "d-1"
    stub["bulk_delete"].assert_called_once_with("u-1", "t-1")
    assert stub["created"] == [("u-1", "t-1", None, None, None, None)]


def test_unknown_user_creates_nothing(monkeypatch, stub):
    rethink = MagicMock()
    rethink.table.return_value.get.return_value.run.return_value = None
    monkeypatch.setattr(mod, "r", rethink)

    with pytest.raises(Error):
        DNP.new_desktop("ghost", "t-1")
    assert stub["created"] == []


# ─── Leaving ``actual``: the one-per-template rule catches up ────────────


@pytest.fixture
def modes(monkeypatch, stub):
    """Each user's frontend mode, as a matching rule would set it."""
    by_user = {}
    monkeypatch.setattr(
        mod.Helpers,
        "gen_payload_from_user",
        staticmethod(lambda user_id, invalidate_cache=False: {"user_id": user_id}),
    )
    monkeypatch.setattr(
        rules,
        "_get_applied_frontend_mode_rule",
        lambda payload: {"frontend_mode": by_user[payload["user_id"]]},
    )
    return by_user


def _temporals(stub, *temporals):
    """Stub the non-persistent desktops the sweep reads."""
    query = stub["rethink"].table.return_value.get_all.return_value
    query.filter.return_value.pluck.return_value.run.return_value = [
        {"user": user, "from_template": template, "status": status}
        for user, template, status in temporals
    ]


@pytest.mark.parametrize(
    "mode",
    [
        pytest.param("deprecated", id="deprecated"),
        pytest.param("all", id="all"),
        pytest.param("hidden", id="hidden"),
    ],
)
def test_sweep_deletes_the_temporals_of_a_template_held_several_times_off_actual(
    stub, modes, mode
):
    modes["u-1"] = mode
    _temporals(
        stub,
        ("u-1", "t-1", "Started"),
        ("u-1", "t-1", "Stopped"),
        ("u-1", "t-2", "Started"),
    )

    DNP.enforce_single_temporal_per_template()

    assert stub["bulk_delete"].call_args_list == [(("u-1", "t-1"),)]


def test_sweep_keeps_the_temporals_of_a_user_on_actual(stub, modes):
    modes.update({"u-actual": "actual", "u-all": "all"})
    _temporals(
        stub,
        ("u-actual", "t-1", "Started"),
        ("u-actual", "t-1", "Started"),
        ("u-all", "t-1", "Started"),
        ("u-all", "t-1", "Started"),
    )

    DNP.enforce_single_temporal_per_template()

    assert stub["bulk_delete"].call_args_list == [(("u-all", "t-1"),)]


def test_sweep_leaves_the_slot_alone_when_the_other_temporal_is_being_deleted(
    stub, modes
):
    """A temporal replacing one still on its way out is not an extra."""
    modes["u-1"] = "all"
    _temporals(stub, ("u-1", "t-1", "Started"), ("u-1", "t-1", "ForceDeleting"))

    DNP.enforce_single_temporal_per_template()

    stub["bulk_delete"].assert_not_called()


def test_sweep_reads_only_the_given_users_desktops(stub, modes):
    modes.update({"u-1": "all", "u-2": "all"})
    _temporals(stub)

    DNP.enforce_single_temporal_per_template(["u-1", "u-2"])

    stub["rethink"].table.return_value.get_all.assert_called_once_with(
        ["desktop", "u-1"], ["desktop", "u-2"], index="kind_user"
    )


def test_sweep_reads_every_desktop_without_users(stub, modes):
    _temporals(stub)

    DNP.enforce_single_temporal_per_template()

    stub["rethink"].table.return_value.get_all.assert_called_once_with(
        "desktop", index="kind"
    )


def test_sweep_reads_nothing_for_an_empty_user_list(stub, modes):
    DNP.enforce_single_temporal_per_template([])

    stub["rethink"].table.return_value.get_all.assert_not_called()


def test_sweep_goes_on_past_a_user_it_can_not_read(stub, modes):
    modes["u-2"] = "all"  # u-1 vanished: reading its mode fails
    _temporals(
        stub,
        ("u-1", "t-1", "Started"),
        ("u-1", "t-1", "Started"),
        ("u-2", "t-1", "Started"),
        ("u-2", "t-1", "Started"),
    )

    DNP.enforce_single_temporal_per_template()

    assert stub["bulk_delete"].call_args_list == [(("u-2", "t-1"),)]
