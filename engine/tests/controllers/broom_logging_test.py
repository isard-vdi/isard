"""Every corrective write the broom makes must leave one findable line.

The broom acting means another component did not converge the row, so an
installation where it acts is an installation with something wrong. Before
this, two of its writes were logged at DEBUG — invisible under the production
INFO level — and one was not logged at all, so that question could not be
answered from a log at all.

What is pinned: the token, the level, the fields, and that each action emits
exactly one line.
"""

from time import time
from unittest.mock import MagicMock, patch

import pytest

import engine.controllers.broom as mod


def _rendered(call):
    """Render one ``logger.warning(fmt, *args)`` call the way logging would."""
    args = call.args
    return args[0] % tuple(args[1:])


def _fields(call):
    """Parse the ``key=value`` tail of a rendered line."""
    return dict(
        pair.split("=", 1) for pair in _rendered(call).split(" ")[1:] if "=" in pair
    )


class _Emitted:
    """The broom's log calls for one block, by level.

    ``engine.services.log`` is stubbed as a ``MagicMock`` by the engine
    conftest, so the broom's ``logs.broom`` is a mock and no handler ever sees
    a record. Read the calls instead — which also states the level directly,
    since the level IS the method name.
    """

    def __init__(self, logger):
        self._logger = logger

    def _calls(self, level):
        return [
            call
            for call in getattr(self._logger, level).call_args_list
            if call.args and isinstance(call.args[0], str)
        ]

    def with_token(self, token, level=None):
        levels = [level] if level else ["warning", "info", "error", "debug"]
        return [
            (lvl, call)
            for lvl in levels
            for call in self._calls(lvl)
            if _rendered(call).startswith(token)
        ]


@pytest.fixture
def acted():
    logger = mod.logs.broom
    logger.reset_mock()
    yield _Emitted(logger)
    logger.reset_mock()


def _domain(domain_id, status, hyp_started=False, accessed=None):
    return {
        "id": domain_id,
        "status": status,
        "hyp_started": hyp_started,
        "accessed": int(time()) if accessed is None else accessed,
    }


def _one_pass(domains, active_by_hyp=None):
    manager = MagicMock()
    manager.check_actions_domains_enabled.return_value = True
    broom = mod.ThreadBroom(name="broom-log-test", polling_interval=0, manager=manager)

    def _stop(_data):
        broom.stop = True

    with patch.object(
        mod, "get_domains_with_transitional_status", return_value=domains
    ), patch.object(
        mod, "get_hyp_hostnames_online", return_value={"hyp-1": "host-1"}
    ), patch.object(
        broom, "_check_hypervisors_concurrent", return_value=(active_by_hyp or {})
    ), patch.object(
        mod, "update_domain_status", MagicMock()
    ), patch.object(
        mod, "update_domain_hyp_started", MagicMock()
    ), patch.object(
        mod, "update_vgpu_info_if_stopped", MagicMock()
    ), patch.object(
        mod, "format_broom_data", _stop
    ):
        broom.polling()
    broom.stop_thread()


ACTIONS = [
    (
        "orphan_without_hypervisor",
        [_domain("d-1", "Shutting-down")],
        None,
        {"from": "Shutting-down", "to": "Unknown", "hyp": "-"},
        mod.UPSTREAM_FAILURE,
    ),
    (
        "stop_without_hypervisor",
        [_domain("d-1", "Stopping")],
        None,
        {"from": "Stopping", "to": "Stopped", "hyp": "-"},
        mod.UPSTREAM_FAILURE,
    ),
    (
        "stop_vanished_from_libvirt",
        [_domain("d-1", "Stopping", hyp_started="hyp-1")],
        {"hyp-1": {"active_domains": {}}},
        {"from": "Stopping", "to": "Stopped", "hyp": "hyp-1"},
        mod.UPSTREAM_FAILURE,
    ),
    (
        "fail_stuck_reset",
        [_domain("d-1", "Resetting", hyp_started="hyp-1", accessed=int(time()) - 300)],
        {"hyp-1": {"active_domains": {}}},
        {"from": "Resetting", "to": "Failed", "hyp": "hyp-1"},
        mod.UPSTREAM_FAILURE,
    ),
    (
        "stop_finished_shutdown",
        [_domain("d-1", "Shutting-down", hyp_started="hyp-1")],
        {"hyp-1": {"active_domains": {}}},
        {"from": "Shutting-down", "to": "Stopped", "hyp": "hyp-1"},
        mod.UPSTREAM_FAILURE,
    ),
    (
        "force_stop_after_shutdown_timeout",
        [
            _domain(
                "d-1", "Shutting-down", hyp_started="hyp-1", accessed=int(time()) - 3600
            )
        ],
        {"hyp-1": {"active_domains": {"d-1": {"status": "Started", "detail": ""}}}},
        {"from": "Shutting-down", "to": "Stopping", "hyp": "hyp-1"},
        mod.EXPECTED,
    ),
]


@pytest.mark.parametrize(
    "action,domains,active,expected,kind", ACTIONS, ids=[case[0] for case in ACTIONS]
)
def test_each_corrective_write_emits_one_findable_line(
    acted, action, domains, active, expected, kind
):
    _one_pass(domains, active)

    lines = acted.with_token(mod.BROOM_ACTED)
    assert len(lines) == 1, [r.getMessage() for r in lines]

    level, call = lines[0]
    fields = _fields(call)
    assert fields["action"] == action
    assert fields["domain"] == "d-1"
    assert fields["class"] == kind
    for key, value in expected.items():
        assert fields[key] == value
    assert fields["reason"] != "-"


@pytest.mark.parametrize(
    "action,domains,active,expected,kind", ACTIONS, ids=[case[0] for case in ACTIONS]
)
def test_the_level_separates_a_defect_from_ordinary_work(
    acted, action, domains, active, expected, kind
):
    """A WARNING from the broom means something upstream failed to converge.

    That is what makes ``|= "BROOM_ACTED"`` filterable down to real problems
    instead of every stop the broom ever finished.
    """
    _one_pass(domains, active)

    level, _call = acted.with_token(mod.BROOM_ACTED)[0]
    assert level == ("warning" if kind == mod.UPSTREAM_FAILURE else "info")


def test_only_a_guest_ignoring_acpi_is_ordinary():
    """Seven of the eight corrections mean a defect; pin which one does not."""
    ordinary = {action for action, _d, _a, _e, kind in ACTIONS if kind == mod.EXPECTED}

    assert ordinary == {"force_stop_after_shutdown_timeout"}


def test_a_pass_that_corrects_nothing_says_nothing(acted):
    """A healthy installation must stay silent, or the signal is worthless."""
    _one_pass(
        [_domain("d-1", "Started", hyp_started="hyp-1")],
        {"hyp-1": {"active_domains": {"d-1": {"status": "Started", "detail": ""}}}},
    )

    assert acted.with_token(mod.BROOM_ACTED) == []


def test_a_domain_the_database_never_heard_of_is_reported_as_destroyed(acted):
    connection = MagicMock()
    connection.connected = True
    connection.get_domains.return_value = {"ghost": {"status": "Started", "detail": ""}}
    connection.get_storage_used.return_value = {}
    with patch.object(
        mod, "get_hyp_hostname_from_id", return_value=("h", 22, "u", False, None)
    ), patch.object(mod, "hyp", return_value=connection), patch.object(
        mod, "get_domain_status", return_value=None
    ), patch.object(
        mod, "update_table_dict", MagicMock()
    ):
        mod._check_single_hypervisor("hyp-1", 0, set())

    lines = acted.with_token(mod.BROOM_ACTED)
    assert len(lines) == 1
    fields = _fields(lines[0][1])
    assert fields["action"] == "destroy_domain_absent_from_database"
    assert fields["class"] == mod.UPSTREAM_FAILURE
    assert fields["domain"] == "ghost"
    assert fields["hyp"] == "hyp-1"


def test_the_token_is_one_word_so_a_log_query_can_match_it():
    assert " " not in mod.BROOM_ACTED and mod.BROOM_ACTED.isupper()


class TestThePassReportsItsOwnDuration:
    def test_every_pass_reports_its_seconds(self, acted):
        _one_pass([_domain("d-1", "Started", hyp_started="hyp-1")], {})

        lines = acted.with_token(mod.BROOM_PASS)
        assert len(lines) == 1
        fields = _fields(lines[0][1])
        assert float(fields["seconds"]) >= 0
        assert fields["overrun"] == "no"
        assert fields["hypervisors"] == "1"

    def test_a_pass_that_outlasts_its_interval_is_a_warning(self, acted):
        """It cannot keep up with the fleet, and the next pass starts late."""
        mod.log_broom_pass(12.0, 10, domains=400, hypervisors=30)

        level, call = acted.with_token(mod.BROOM_PASS)[0]
        assert level == "warning"
        fields = _fields(call)
        assert fields["overrun"] == "yes"
        assert fields["seconds"] == "12.00"
        assert fields["domains"] == "400"

    def test_a_pass_within_its_interval_is_not(self, acted):
        mod.log_broom_pass(1.5, 10, domains=400, hypervisors=30)

        level, call = acted.with_token(mod.BROOM_PASS)[0]
        assert level == "info"
        assert _fields(call)["overrun"] == "no"

    def test_an_unscheduled_pass_cannot_overrun(self, acted):
        """``polling_interval=0`` is the tests' own driving, not a fleet."""
        mod.log_broom_pass(9.0, 0, domains=1, hypervisors=1)

        assert _fields(acted.with_token(mod.BROOM_PASS)[0][1])["overrun"] == "no"
