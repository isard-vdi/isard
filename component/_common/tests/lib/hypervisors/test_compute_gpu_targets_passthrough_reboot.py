#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""compute_gpu_targets must re-apply a passthrough card after a host reboot.

Regression: a passthrough-only board whose SR-IOV hardware exposes
``totalvfs>0`` reports no vGPU profiles while still bound to the nvidia
driver, so hypervisor discovery emits the ``vgpu_profiles=None`` "discovery
failed" sentinel. compute_gpu_targets used to skip every ``None`` card
outright, so such a card was never given a target at registration: its vgpus
row (recreated empty on restart) stayed un-applied, the scheduler could not
place it ("Could not place all 1 requested vGPU profiles ... distinct free
cards"), and it had to be re-forced by hand with a profile PUT after EVERY
boot.

The fix still leaves a ``None`` card to the engine when its durable intent is a
real vGPU profile (never guess a carve during a discovery failure), but emits a
passthrough target when the durable operator intent is passthrough -- the only
case that is both safe (passthrough binding is idempotent, never destroys a
vGPU carve) and necessary (otherwise the card is unplaceable forever).
"""

import contextlib
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def hyper(monkeypatch):
    from isardvdi_common.lib.hypervisors import hypervisors as mod

    cls = mod.HypervisorsProcessed

    state = {"gpus": [], "vgpus": {}}

    class _Filter:
        def __init__(self, rows):
            self._rows = rows

        def pluck(self, *_a, **_k):
            return self

        def run(self, _conn):
            return list(self._rows)

    class _Get:
        def __init__(self, row):
            self._row = row

        def run(self, _conn):
            return self._row

    class _Table:
        def __init__(self, name):
            self.name = name

        def filter(self, criteria):
            dev = criteria.get("physical_device")
            return _Filter(
                [g for g in state["gpus"] if g.get("physical_device") == dev]
            )

        def get(self, row_id):
            return _Get(state["vgpus"].get(row_id))

    monkeypatch.setattr(mod.r, "table", lambda name: _Table(name))
    # Patch _rdb_connection on the metaclass: it is a property with no deleter,
    # so patching it on cls makes monkeypatch's teardown delattr and raise.
    monkeypatch.setattr(
        type(cls),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    monkeypatch.setattr(
        cls, "_rdb_context", classmethod(lambda c: contextlib.nullcontext())
    )
    monkeypatch.setattr(
        cls,
        "_vgpu_id_for",
        classmethod(lambda c, hyper_id, pci: f"{hyper_id}-{pci}"),
    )
    # Not reached on the None branch, but stub defensively so an accidental
    # fall-through fails loudly rather than hitting the DB / a live scheduler.
    monkeypatch.setattr(
        cls,
        "get_vgpu_scheduled_profile_now",
        classmethod(lambda c, card_id: None),
    )
    return cls, state


def _gpu(pci, vgpu_profiles):
    return {
        "pci_bus_id": pci,
        "_resolved_model": "RTX_PRO_4000",
        "vgpu_profiles": vgpu_profiles,
        "current_profile": None,
    }


def test_none_card_with_durable_passthrough_intent_is_reapplied(hyper):
    cls, state = hyper
    hyper_id, pci = "isard-hypervisor", "pci_0000_01_00_0"
    vgpu_id = f"{hyper_id}-{pci}"
    # Durable operator intent = passthrough (what a profile PUT persists), and a
    # fresh/empty vgpus row as after a hypervisor restart.
    state["gpus"] = [
        {
            "id": "gpu-4000",
            "physical_device": vgpu_id,
            "operator_requested_profile": "passthrough",
            "operator_passthrough": True,
        }
    ]
    state["vgpus"] = {vgpu_id: {}}

    targets = cls.compute_gpu_targets(hyper_id, [_gpu(pci, None)])

    assert pci in targets, "passthrough card with None discovery must be targeted"
    assert targets[pci]["target_profile"] == "passthrough"
    assert targets[pci]["action"] == "apply"
    assert targets[pci]["card_id"] == "gpu-4000"


def test_none_card_with_vgpu_intent_is_left_to_the_engine(hyper):
    cls, state = hyper
    hyper_id, pci = "isard-hypervisor", "pci_0000_41_00_0"
    vgpu_id = f"{hyper_id}-{pci}"
    # Durable intent is a REAL vGPU profile -> during a discovery failure we must
    # NOT guess a carve; leave the card to the engine (no target emitted).
    state["gpus"] = [
        {
            "id": "gpu-a16",
            "physical_device": vgpu_id,
            "operator_requested_profile": "2Q",
            "operator_passthrough": False,
        }
    ]
    state["vgpus"] = {vgpu_id: {}}

    targets = cls.compute_gpu_targets(hyper_id, [_gpu(pci, None)])

    assert pci not in targets, "a vGPU-intent card must not be force-passthroughed"
