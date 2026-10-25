"""A GPU start that fails before it is queued releases its in-flight memory charge."""

import sys
from unittest.mock import MagicMock

import pytest

_rethinkdb_stubs = {
    name: sys.modules.pop(name)
    for name in list(sys.modules)
    if name == "rethinkdb" or name.startswith("rethinkdb.")
}
try:
    import engine.controllers.ui_actions as ui
finally:
    sys.modules.update(_rethinkdb_stubs)

for _name, _value in {"log": None, "logs": None, "LOG_LEVEL": "INFO"}.items():
    if not hasattr(ui, _name):
        setattr(
            ui,
            _name,
            MagicMock(name=f"ui_actions.{_name}") if _value is None else _value,
        )

DOMAIN_XML = (
    "<domain type='kvm'><name>d</name>"
    "<memory unit='KiB'>8388608</memory><vcpu>2</vcpu>"
    "<os><type arch='x86_64' machine='pc-q35-8.2'>hvm</type></os>"
    "<devices><emulator>/usr/bin/qemu-kvm</emulator></devices></domain>"
)


def _card(n):
    return {"nvidia": True, "gpu_id": f"gpu{n}", "uid": f"uid{n}", "profile": "p"}


@pytest.fixture
def start(monkeypatch):
    def _run(selections, xml_error=False):
        released, queued = [], []
        monkeypatch.setattr(
            ui, "release_pending_start", lambda h, d: released.append((h, d))
        )
        monkeypatch.setattr(ui, "update_vgpu_uuid_domain_action", lambda *a, **k: True)
        monkeypatch.setattr(ui, "update_domain_status", lambda *a, **k: None)
        if xml_error:

            def _fail(*a, **k):
                raise ValueError("bad xml")

            monkeypatch.setattr(ui, "recreate_xml_if_gpu", _fail)
        else:
            monkeypatch.setattr(ui, "recreate_xml_if_gpu", lambda xml, *a, **k: xml)

        balancer = MagicMock()
        balancer.get_next_hypervisor.side_effect = list(selections)

        class _Pool:
            pass

        _Pool.balancer = balancer
        workers = MagicMock()
        workers.__getitem__.return_value.put.side_effect = lambda *a: queued.append(a)

        class _Manager:
            pools = {"default": _Pool()}
            q = MagicMock(workers=workers)

        actions = ui.UiActions.__new__(ui.UiActions)
        actions.manager = _Manager()
        result = actions.start_domain_from_xml(
            DOMAIN_XML,
            "desktop",
            pool_id="default",
            storage_pool_id="pool",
            domain_memory_gb=8,
            reservables={"vgpus": ["p", "p"]},
        )
        return result, released, queued

    return _run


def test_a_second_card_that_cannot_be_placed_releases_the_host_charge(start):
    result, released, queued = start([("h1", _card(1)), (False, {})])

    assert result is False
    assert released == [("h1", "desktop")]
    assert not queued


def test_a_gpu_xml_injection_failure_releases_the_host_charge(start):
    result, released, queued = start([("h1", _card(1))], xml_error=True)

    assert result is False
    assert released == [("h1", "desktop")]
    assert not queued
