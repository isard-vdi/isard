#!/usr/bin/env python3
"""Refuse a domain start whose GPU hostdev references a card mid profile-change.

Reads the domain XML on stdin. Exit 0 = allow the start; exit 3 = refuse it (a
referenced GPU card's PF has a fresh ``/run/isard-gpu-change.<pf-bdf>`` marker
written by ``gpu_apply_cli`` for the duration of a runtime profile change).

Called from the libvirt qemu hook on ``prepare``/``start`` -- BEFORE qemu
launches -- so a start that raced the engine's placement veto cannot re-grab a
card being torn down (which would wedge the PF in D-state). This is the
authoritative host-side half of the start-block; the engine's
``changing_to_profile`` veto is the first line. MUST NOT call virsh (a libvirt
hook that calls virsh deadlocks libvirtd).
"""

import os
import re
import sys
import time

MARKER_DIR = "/run"
MARKER_PREFIX = "isard-gpu-change."
MARKER_TTL = 300  # s; a marker older than this is stale (crashed CLI) -> ignored

_PCI_HOSTDEV_RE = re.compile(
    r"<hostdev\b[^>]*type=['\"]pci['\"][^>]*>(.*?)</hostdev>", re.S
)
_ADDR_RE = re.compile(
    r"<address[^>]*domain=['\"](0x[0-9a-fA-F]+)['\"]"
    r"[^>]*bus=['\"](0x[0-9a-fA-F]+)['\"]"
    r"[^>]*slot=['\"](0x[0-9a-fA-F]+)['\"]"
    r"[^>]*function=['\"](0x[0-9a-fA-F]+)['\"]"
)
_UUID_RE = re.compile(r"uuid=['\"]([0-9a-fA-F-]{36})['\"]")
_BDF_RE = re.compile(r"^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]$")


def _pf_of(bdf):
    """The PF bdf for a device bdf: the physfn target if it's an SR-IOV VF,
    else the bdf itself (markers are keyed by the PF)."""
    physfn = f"/sys/bus/pci/devices/{bdf}/physfn"
    if os.path.islink(physfn):
        try:
            return os.path.basename(os.path.realpath(physfn))
        except OSError:
            return bdf
    return bdf


def cards_from_xml(xml):
    """PF bdfs of every GPU this domain XML attaches (PCI passthrough hostdevs
    and mdev/vGPU hostdevs resolved to their parent PF)."""
    cards = set()
    for block in _PCI_HOSTDEV_RE.findall(xml):
        a = _ADDR_RE.search(block)
        if a:
            dom_, bus, slot, func = (int(x, 16) for x in a.groups())
            cards.add(_pf_of(f"{dom_:04x}:{bus:02x}:{slot:02x}.{func:x}"))
    for uuid in _UUID_RE.findall(xml):
        try:
            parent = os.path.basename(
                os.path.dirname(os.path.realpath(f"/sys/bus/mdev/devices/{uuid}"))
            )
        except OSError:
            continue
        if _BDF_RE.match(parent):
            cards.add(_pf_of(parent))
    return cards


def card_changing(pf_bdf, now=None):
    """True if a fresh profile-change marker exists for this PF."""
    path = os.path.join(MARKER_DIR, MARKER_PREFIX + pf_bdf)
    try:
        age = (now or time.time()) - os.path.getmtime(path)
    except OSError:
        return False
    return age < MARKER_TTL


def main(xml=None):
    xml = sys.stdin.read() if xml is None else xml
    for pf in cards_from_xml(xml):
        if card_changing(pf):
            sys.stderr.write(
                f"gpu_change_guard: refuse start -- card {pf} mid profile-change\n"
            )
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
