"""A degraded hypervisor's queue stays put while the shared storage is stalled."""

from unittest.mock import MagicMock, patch

import pytest

from engine.models import hypervisor_orchestrator as mod

ACTION = {"type": "hyp_degraded", "hyp_id": "hyp-1", "reason": "storage: x"}


def _thread():
    t = mod.HypervisorsOrchestratorThread.__new__(mod.HypervisorsOrchestratorThread)
    t.manager = MagicMock()
    t.d_queues = {"workers": {}}
    return t


@patch.object(mod, "move_actions_to_others_hypers")
def test_no_queue_moves_during_a_stall(move):
    with patch.object(mod, "get_shared_storage_stall", return_value={"active": True}):
        _thread().handle_hyp_degraded(ACTION)
    move.assert_not_called()


@pytest.mark.parametrize(
    "stored",
    [None, {"active": False, "cleared_at": 1.0}, MagicMock()],
)
@patch.object(mod, "move_actions_to_others_hypers")
def test_queues_move_otherwise(move, stored):
    with patch.object(mod, "get_shared_storage_stall", return_value=stored):
        _thread().handle_hyp_degraded(ACTION)
    assert move.call_args.args[0] == "hyp-1"


@patch.object(mod, "move_actions_to_others_hypers")
def test_an_unreadable_condition_does_not_stop_the_move(move):
    with patch.object(
        mod, "get_shared_storage_stall", side_effect=RuntimeError("db down")
    ):
        _thread().handle_hyp_degraded(ACTION)
    move.assert_called_once()
