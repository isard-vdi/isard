"""The registry of domains a hypervisor may still be running."""

import json
from unittest.mock import MagicMock

import pytest

from engine.services.lib import domain_guard as mod


@pytest.fixture(autouse=True)
def redis(monkeypatch):
    mirrored = {}

    def mirror(domain_id, entry):
        if entry is None:
            mirrored.pop(domain_id, None)
        else:
            mirrored[domain_id] = json.loads(json.dumps(entry))

    monkeypatch.setattr(mod, "_mirror", mirror)
    mod._held.clear()
    yield mirrored
    mod._held.clear()


def test_hold_and_release(redis):
    mod.hold("d-1", "hyp-1", "destroy")
    assert mod.holder("d-1")["hyp_id"] == "hyp-1"
    assert redis["d-1"]["operation"] == "destroy"

    assert mod.release("d-1") is True
    assert mod.holder("d-1") is None
    assert "d-1" not in redis


def test_another_hypervisor_cannot_release_it():
    mod.hold("d-1", "hyp-1", "destroy")
    assert mod.release("d-1", "hyp-2") is False
    assert mod.holder("d-1") is not None


def test_releasing_nothing_is_harmless():
    assert mod.release("d-404") is False


def test_holder_is_a_copy():
    mod.hold("d-1", "hyp-1", "createXML")
    mod.holder("d-1")["hyp_id"] = "changed"
    assert mod.holder("d-1")["hyp_id"] == "hyp-1"


def test_reset_forgets_everything(monkeypatch):
    mod.hold("d-1", "hyp-1", "destroy")
    fake = MagicMock()
    import isardvdi_common.connections.redis_base as redis_base

    monkeypatch.setattr(redis_base.RedisBase, "_redis", fake)
    mod.reset()
    assert mod.holder("d-1") is None
    fake.delete.assert_called_once_with(mod.REDIS_KEY)


def test_a_redis_outage_never_breaks_a_hold(monkeypatch):
    monkeypatch.undo()
    import isardvdi_common.connections.redis_base as redis_base

    broken = MagicMock()
    broken.hset.side_effect = ConnectionError("down")
    monkeypatch.setattr(redis_base.RedisBase, "_redis", broken)
    mod.hold("d-1", "hyp-1", "destroy")
    assert mod.holder("d-1") is not None
