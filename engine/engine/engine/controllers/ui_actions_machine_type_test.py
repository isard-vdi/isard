"""The machine-type normalisation at its CALL SITE, not just as a function.

``normalize_machine_type`` is pure and well covered, and that is exactly what
made this blind: the call site is where it broke. It shipped once with
``domain_is_raw(domain)`` naming a variable this function does not have, inside
the IF CONDITION, so the NameError escaped the try/except right below it and
killed the start with no detail and nothing in the log -- the desktop stayed in
Starting for ever. Every unit test stayed green.

``controllers/ui_actions`` pulls the engine's DB, libvirt and rethink stack, so
these run where ``unit-test-engine`` runs them: inside the engine image, with
``conftest.py`` stubbing ``engine.services.db*`` as MagicMock. ``domain_xml``
is deliberately NOT stubbed, so the real normaliser runs.
"""

import re
import sys
from unittest.mock import MagicMock

import pytest

# conftest's `rethinkdb` stub is a MagicMock, not a package, so the
# `from rethinkdb.errors import ...` that isardvdi_common does at import time
# fails. Lift it for this import only; `engine.services.db*` stays stubbed.
_rethinkdb_stubs = {
    name: sys.modules.pop(name)
    for name in list(sys.modules)
    if name == "rethinkdb" or name.startswith("rethinkdb.")
}
try:
    import engine.controllers.ui_actions as ui
finally:
    sys.modules.update(_rethinkdb_stubs)

# A star-import over conftest's MagicMock brings in nothing, so the names
# `engine.services.log` provides are absent and any logging call raises
# NameError. Supply only these three: injecting whatever a NameError asks for
# would hide the exact defect these tests exist to catch.
_LOG_STAR_NAMES = {"log": None, "logs": None, "LOG_LEVEL": "INFO"}
for _name, _value in _LOG_STAR_NAMES.items():
    if not hasattr(ui, _name):
        setattr(
            ui,
            _name,
            MagicMock(name=f"ui_actions.{_name}") if _value is None else _value,
        )

ACCEPTED = ["pc-i440fx-5.1", "pc-i440fx-8.2", "pc-q35-6.1", "pc-q35-10.0"]

DOMAIN_XML = (
    "<domain type='kvm'><name>d</name>"
    "<memory unit='KiB'>1048576</memory><vcpu>2</vcpu>"
    "<os><type arch='x86_64' machine='{machine}'>hvm</type><boot dev='hd'/></os>"
    "<devices><emulator>/usr/bin/qemu-kvm</emulator></devices></domain>"
)


class _Queue:
    def __init__(self, box):
        self.box = box

    def qsize(self):
        return 0

    def put(self, action, priority):
        self.box["action"] = action


class _Workers(dict):
    def __init__(self, box):
        self.box = box

    def __getitem__(self, key):
        return _Queue(self.box)


def _manager(box, hyp="hyper-1"):
    class _Balancer:
        def get_next_hypervisor(self, **kwargs):
            return hyp, {}

    class _Pool:
        balancer = _Balancer()

    class _Q:
        workers = _Workers(box)

    class _Manager:
        pools = {"default": _Pool()}
        q = _Q()

    return _Manager()


@pytest.fixture
def start(monkeypatch):
    """Drive the real start_domain_from_xml and hand back the queued XML."""

    def _run(machine, accepted=ACCEPTED, protected=None, hyp="hyper-1"):
        box = {}
        ui.log.warning.reset_mock()
        monkeypatch.setattr(
            ui,
            "get_domain",
            lambda _id: {"create_dict": {"xml_protected_sections": protected or []}},
        )
        seen = {}

        def _machine_types(hyp_id):
            seen["hyp_id"] = hyp_id
            return accepted

        monkeypatch.setattr(ui, "get_hyp_machine_types", _machine_types)
        actions = ui.UiActions.__new__(ui.UiActions)
        actions.manager = _manager(box, hyp)
        actions.start_domain_from_xml(
            DOMAIN_XML.format(machine=machine), "desktop-1", pool_id="default"
        )
        queued = box.get("action")
        assert queued is not None, "nothing was queued -- the start died"
        # lxml re-serialises with double quotes, so the corrected XML does not
        # look like the one that went in -- accept either quoting.
        found = re.search(r"machine=[\"']([^\"']+)", queued["xml"])
        seen["warnings"] = [
            str(call.args[0]) for call in ui.log.warning.call_args_list if call.args
        ]
        return (found.group(1) if found else None), seen

    return _run


def test_a_removed_machine_type_reaches_the_queue_corrected(start):
    """The end-to-end point: what the worker gets must be startable."""
    machine, _seen = start("pc-i440fx-2.8")
    assert machine == "pc-i440fx-5.1"


def test_the_correction_is_reported_with_both_machine_types(start):
    """The operator has to be able to tell a corrected start from a normal one,
    and to see WHAT was corrected -- the original failure was invisible for
    exactly this reason."""
    _machine, seen = start("pc-i440fx-2.8")
    said = " ".join(seen["warnings"])
    assert "pc-i440fx-2.8" in said and "pc-i440fx-5.1" in said


def test_it_asks_the_hypervisor_the_balancer_actually_chose(start):
    """Not a global, not the first row: the host this domain is going to."""
    _machine, seen = start("pc-i440fx-2.8", hyp="hyper-7")
    assert seen["hyp_id"] == "hyper-7"


def test_an_accepted_machine_type_is_queued_untouched(start):
    machine, _seen = start("pc-i440fx-8.2")
    assert machine == "pc-i440fx-8.2"


def test_a_raw_domain_is_left_for_libvirt_to_refuse(start):
    """RAW means the admin's XML is authoritative; an invalid value there is
    meant to fail, loudly."""
    machine, _seen = start("pc-i440fx-2.8", protected=["raw"])
    assert machine == "pc-i440fx-2.8"


def test_a_hypervisor_that_reported_nothing_changes_nothing(start):
    """An empty list is "we do not know". Reading it as "supports nothing"
    would rewrite every domain in the installation on a failed probe."""
    machine, _seen = start("pc-i440fx-2.8", accepted=[])
    assert machine == "pc-i440fx-2.8"


def test_a_failure_in_the_lookup_never_blocks_the_start(start, monkeypatch):
    """The guard has to cover the CONDITION too, not just the body: that is
    exactly how the NameError escaped and left the desktop in Starting."""
    box = {}
    monkeypatch.setattr(ui, "get_domain", lambda _id: {})

    def _boom(_hyp_id):
        raise RuntimeError("rethink is down")

    monkeypatch.setattr(ui, "get_hyp_machine_types", _boom)
    actions = ui.UiActions.__new__(ui.UiActions)
    actions.manager = _manager(box)
    actions.start_domain_from_xml(
        DOMAIN_XML.format(machine="pc-i440fx-2.8"), "desktop-1", pool_id="default"
    )
    assert box.get("action") is not None, "a lookup failure must not kill the start"
    assert "pc-i440fx-2.8" in box["action"]["xml"]
