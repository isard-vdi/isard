# SPDX-License-Identifier: AGPL-3.0-or-later

"""The qemu-kvm emulator wrapper: guests are never offered checksum offload."""

import re
import subprocess
from pathlib import Path

import pytest

_HYPERVISOR = Path(__file__).resolve().parents[1]
_WRAPPER = _HYPERVISOR / "kvm" / "qemu-kvm"
_REAL_QEMU = "/usr/bin/qemu-system-x86_64"

_OFFLOADS_OFF = [
    "virtio-net-device.csum=off",
    "virtio-net-device.host_tso4=off",
    "virtio-net-device.host_tso6=off",
    "virtio-net-device.host_ecn=off",
    "virtio-net-device.host_ufo=off",
    "virtio-net-device.host_uso=off",
    "virtio-net-device.host_tunnel=off",
    "virtio-net-device.host_tunnel_csum=off",
]


def _workspace_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "uv.lock").is_file():
            return candidate
    raise RuntimeError("uv workspace root not found above this test")


@pytest.fixture
def run_wrapper(tmp_path):
    fake = tmp_path / "qemu-system-x86_64"
    fake.write_text('#!/bin/sh\necho "AUDIO=$QEMU_AUDIO_DRV"\nprintf \'%s\\n\' "$@"\n')
    fake.chmod(0o755)
    source = _WRAPPER.read_text()
    assert source.count(_REAL_QEMU) == 1
    wrapper = tmp_path / "qemu-kvm"
    wrapper.write_text(source.replace(_REAL_QEMU, str(fake)))

    def run(*args):
        out = subprocess.run(
            ["sh", str(wrapper), *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
        return out.splitlines()

    return run


def test_every_virtio_net_offload_is_disabled(run_wrapper):
    lines = run_wrapper("-name", "guest=d1")
    globals_ = [lines[i + 1] for i, a in enumerate(lines) if a == "-global"]
    assert globals_ == _OFFLOADS_OFF


def test_libvirt_arguments_pass_through_untouched_and_last(run_wrapper):
    libvirt_args = [
        "-name",
        "guest=a b,debug-threads=on",
        "-device",
        "virtio-net-pci,id=net0",
    ]
    lines = run_wrapper(*libvirt_args)
    assert lines[0] == "AUDIO=spice"
    assert lines[-len(libvirt_args) :] == libvirt_args


def test_wrapper_is_the_emulator_the_engine_writes_into_every_domain():
    dockerfile = (_HYPERVISOR / "Dockerfile").read_text()
    assert re.search(
        r"^COPY docker/hypervisor/kvm/qemu-kvm /usr/bin/qemu-kvm$", dockerfile, re.M
    )
    domain_xml = (
        _workspace_root() / "engine" / "src" / "engine" / "models" / "domain_xml.py"
    ).read_text()
    assert (
        'def set_domain_type_and_emulator(tree, type="kvm", emulator="/usr/bin/qemu-kvm")'
        in domain_xml
    )
