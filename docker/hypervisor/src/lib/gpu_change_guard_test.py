"""Unit tests for gpu_change_guard (the qemu-hook start-block guard)."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import gpu_change_guard as g  # noqa: E402

_PCI_XML = """<domain><devices>
<hostdev mode='subsystem' type='pci'><source>
<address domain='0x0000' bus='0x03' slot='0x00' function='0x0'/></source></hostdev>
<hostdev mode='subsystem' type='pci'><source>
<address domain='0x0000' bus='0x63' slot='0x00' function='0x0'/></source></hostdev>
</devices></domain>"""


def test_cards_from_xml_pci_hostdevs():
    # No physfn on the test host -> each bdf is its own PF.
    assert g.cards_from_xml(_PCI_XML) == {"0000:03:00.0", "0000:63:00.0"}


# A vendor-specific VFIO vGPU (Ubuntu 24.04+) is an ordinary type='pci'
# passthrough of an SR-IOV VF with display='off' -- NOT an mdev UUID hostdev. It
# must still be guarded: cards_from_xml picks it up via the PCI branch and
# _pf_of resolves the VF to its parent PF (the marker key).
_VFIO_VGPU_XML = """<domain><devices>
<hostdev mode='subsystem' type='pci' managed='yes' display='off'><source>
<address domain='0x0000' bus='0x05' slot='0x00' function='0x4'/></source></hostdev>
</devices></domain>"""


def test_cards_from_xml_guards_vfio_vgpu_vf_hostdev(monkeypatch):
    # The VF 0000:05:00.4 resolves to its PF 0000:05:00.0 (physfn).
    monkeypatch.setattr(
        g, "_pf_of", lambda bdf: "0000:05:00.0" if bdf == "0000:05:00.4" else bdf
    )
    assert g.cards_from_xml(_VFIO_VGPU_XML) == {"0000:05:00.0"}


def test_main_refuses_when_vfio_vgpu_card_is_changing(monkeypatch):
    monkeypatch.setattr(
        g, "_pf_of", lambda bdf: "0000:05:00.0" if bdf == "0000:05:00.4" else bdf
    )
    monkeypatch.setattr(g, "card_changing", lambda pf, now=None: pf == "0000:05:00.0")
    assert g.main(_VFIO_VGPU_XML) == 3  # refuse a start onto a card mid-recarve


def test_main_refuses_when_a_referenced_card_is_changing(monkeypatch):
    monkeypatch.setattr(g, "card_changing", lambda pf, now=None: pf == "0000:63:00.0")
    assert g.main(_PCI_XML) == 3  # refuse


def test_main_allows_when_no_card_changing(monkeypatch):
    monkeypatch.setattr(g, "card_changing", lambda pf, now=None: False)
    assert g.main(_PCI_XML) == 0  # allow


def test_main_allows_domain_without_gpu():
    assert g.main("<domain><devices></devices></domain>") == 0


def test_card_changing_freshness(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "MARKER_DIR", str(tmp_path))
    marker = tmp_path / (g.MARKER_PREFIX + "0000:03:00.0")
    marker.write_text("2_24Q 123\n")
    # Fresh (now == file mtime) -> changing.
    assert g.card_changing("0000:03:00.0", now=marker.stat().st_mtime) is True
    # Stale (now well past TTL) -> not changing.
    assert (
        g.card_changing("0000:03:00.0", now=marker.stat().st_mtime + g.MARKER_TTL + 1)
        is False
    )
    # No marker -> not changing.
    assert g.card_changing("0000:99:00.0") is False
