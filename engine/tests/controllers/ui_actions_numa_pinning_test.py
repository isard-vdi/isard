"""Which desktops the start path pins to a NUMA node."""

import re
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
    "<memory unit='KiB'>4194304</memory><vcpu>4</vcpu>"
    "<os><type arch='x86_64' machine='pc-q35-8.2'>hvm</type></os>"
    "<devices><emulator>/usr/bin/qemu-kvm</emulator>"
    "<disk type='file' device='disk'><driver name='qemu' type='qcow2'/>"
    "<source file='/x.qcow2'/><target dev='vda' bus='virtio'/></disk>"
    "</devices></domain>"
)

PINNING = ("<vcpupin", "<emulatorpin", "<iothreadpin", "<numatune")
GIB = 1048576


def _topology():
    return {
        "libvirt_numa_ok": True,
        "nodes": {"0": {"cpulist": "0-7,64-71"}, "1": {"cpulist": "8-15,72-79"}},
    }


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


def _manager(box, extra_info):
    class _Balancer:
        def get_next_hypervisor(self, **kwargs):
            return "hyper-1", dict(extra_info)

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
    def _run(
        extra_info,
        protected=None,
        reservables=None,
        cputune="",
        memory_gb=4.0,
        action=False,
    ):
        box = {}
        monkeypatch.setattr(
            ui,
            "get_domain",
            lambda _id: {"create_dict": {"xml_protected_sections": protected or []}},
        )
        monkeypatch.setattr(ui, "get_hyp_machine_types", lambda _h: [])
        monkeypatch.setattr(ui, "update_vgpu_uuid_domain_action", lambda *a, **k: True)
        monkeypatch.setattr(ui, "recreate_xml_if_gpu", lambda xml, *a, **k: xml)
        actions = ui.UiActions.__new__(ui.UiActions)
        actions.manager = _manager(box, extra_info)
        xml = DOMAIN_XML.replace("<os>", cputune + "<os>")
        actions.start_domain_from_xml(
            xml,
            "desktop-1",
            pool_id="default",
            reservables=reservables,
            domain_memory_gb=memory_gb,
        )
        assert box.get("action") is not None, "nothing was queued -- the start died"
        return box["action"] if action else box["action"]["xml"]

    return _run


def _pinned(xml):
    return [tag for tag in PINNING if tag in xml]


def test_a_plain_desktop_is_not_pinned(start):
    xml = start({"numa_topology": _topology(), "selected_numa_node": "0"})
    assert _pinned(xml) == []


def test_a_plain_desktop_is_not_pinned_on_any_node(start):
    xml = start({"numa_topology": _topology(), "selected_numa_node": "1"})
    assert _pinned(xml) == []


def test_a_desktop_on_hugepages_is_still_pinned(start):
    xml = start(
        {
            "numa_topology": _topology(),
            "selected_numa_node": "0",
            "hugepages": {"mounted": True, "1G": {"total": 64}},
            "mem_available_kb": 1048576,
            "hugepages_free_kb": 64 * 1048576,
            "min_free_mem_gb": 0,
        }
    )
    assert "<hugepages" in xml
    assert "<vcpupin" in xml and "0-7,64-71" in xml


def test_a_gpu_desktop_is_still_pinned_to_its_card_node(start):
    xml = start(
        {
            "numa_topology": _topology(),
            "nvidia": True,
            "gpu_id": "gpu-1",
            "uid": "uuid-1",
            "profile": "2Q",
            "gpu_numa_node": 1,
        },
        reservables={"vgpus": ["NVIDIA-A16-2Q"]},
    )
    assert "<vcpupin" in xml and "8-15,72-79" in xml


def test_a_protected_cputune_is_left_as_the_admin_wrote_it(start):
    manual = "<cputune><vcpupin vcpu='0' cpuset='3'/></cputune>"
    xml = start(
        {"numa_topology": _topology(), "selected_numa_node": "0"},
        protected=["cputune"],
        cputune=manual,
    )
    assert 'cpuset="3"' in xml or "cpuset='3'" in xml
    assert "0-7,64-71" not in xml


def _hugepages_extra(pool, free_kb):
    return {
        "numa_topology": _topology(),
        "selected_numa_node": "0",
        "hugepages": {"mounted": True, **pool},
        "mem_available_kb": 0,
        "hugepages_free_kb": free_kb,
        "min_free_mem_gb": 0,
    }


def _page_size(xml):
    match = re.search(r"<page size=.(\d+). unit=.([GM]).", xml)
    return match.group(1) + match.group(2) if match else None


def test_half_a_gib_never_gets_1g_pages(start):
    xml = start(_hugepages_extra({"1G": {"total": 64}}, 64 * GIB), memory_gb=0.5)
    assert _page_size(xml) is None


def test_half_a_gib_falls_back_to_2m_pages(start):
    pool = {"1G": {"total": 64}, "2M": {"total": 4096}}
    xml = start(_hugepages_extra(pool, 64 * GIB + 4096 * 2048), memory_gb=0.5)
    assert _page_size(xml) == "2M"


def test_a_whole_gib_multiple_gets_1g_pages(start):
    pool = {"1G": {"total": 64}, "2M": {"total": 4096}}
    xml = start(_hugepages_extra(pool, 64 * GIB + 4096 * 2048), memory_gb=4.0)
    assert _page_size(xml) == "1G"
    assert "<vcpupin" in xml


def test_free_2m_pages_are_not_counted_as_free_1g_pages(start):
    pool = {"1G": {"total": 4}, "2M": {"total": 4096}}
    xml = start(_hugepages_extra(pool, 4096 * 2048), memory_gb=4.0)
    assert _page_size(xml) == "2M"


def _gpu_extra(**hugepages):
    return {
        "numa_topology": _topology(),
        "nvidia": True,
        "gpu_id": "gpu-1",
        "uid": "uuid-1",
        "profile": "2Q",
        "gpu_numa_node": 1,
        **hugepages,
    }


def test_a_gpu_desktop_with_no_fitting_page_size_takes_the_slow_path(start):
    action = start(
        _gpu_extra(
            hugepages={"mounted": True, "1G": {"total": 64}},
            hugepages_free_kb=64 * GIB,
        ),
        reservables={"vgpus": ["NVIDIA-A16-2Q"]},
        memory_gb=0.5,
        action=True,
    )
    assert _page_size(action["xml"]) is None
    assert action.get("expects_slow_createxml") is True
    assert "<vcpupin" in action["xml"]


def test_a_gpu_desktop_on_a_mixed_pool_gets_2m_pages(start):
    action = start(
        _gpu_extra(
            hugepages={"mounted": True, "1G": {"total": 64}, "2M": {"total": 4096}},
            hugepages_free_kb=64 * GIB + 4096 * 2048,
        ),
        reservables={"vgpus": ["NVIDIA-A16-2Q"]},
        memory_gb=0.5,
        action=True,
    )
    assert _page_size(action["xml"]) == "2M"
    assert not action.get("expects_slow_createxml")
