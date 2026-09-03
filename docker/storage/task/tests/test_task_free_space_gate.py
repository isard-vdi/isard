# SPDX-License-Identifier: AGPL-3.0-or-later

"""The destination free-space floor, for every action that writes a whole copy.

``move`` had a floor but it FAILED OPEN: a probe that could not answer let the
copy through, and a source whose size could not be read reserved zero. Both are
the case where the danger is highest — the filesystem is already unhappy — so
the guard was absent exactly when it mattered.

``convert`` and ``disconnect`` had no floor at all, and both write a full second
copy of the disk: ``convert`` a new destination, ``disconnect`` a ``.wo_chain``
sibling in the same directory. On a tight pool either fills the filesystem, and
a full storage node does not spoil one operation — it spoils every write on the
node and leaves rows mid-flight for someone to reconcile later.

These tests pin the decision the ticket asked for, taken once for the three:
**refuse when the space cannot be known**, and apply a floor by default rather
than only when an operator has configured one.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import task  # noqa: E402

# The geometry is now a required kwarg on convert/disconnect; its value is
# irrelevant to the free-space floor, so these tests pass the default policy.
_GEO = {
    "cluster_size": "4k",
    "extended_l2": "off",
    "lazy_refcounts": "off",
    "preallocation": "off",
}


def _sized(tmp_path, name, nbytes):
    p = tmp_path / name
    p.write_bytes(b"\0" * nbytes)
    return str(p)


# --------------------------------------------------------------------------
# move: the two fail-open holes
# --------------------------------------------------------------------------


def test_move_refuses_when_free_space_is_unknown(tmp_path, monkeypatch):
    """``_free_space`` returns None when statvfs fails. Refuse: proceeding here
    is proceeding blind onto the very filesystem the floor exists to protect."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: None)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)

    with pytest.raises(RuntimeError) as excinfo:
        task.move(src, dst, "rsync", min_free_bytes=8192, remove_source_file=False)

    assert "cannot read the free space" in str(excinfo.value)
    assert not Path(dst).exists()
    assert Path(src).exists()


def test_move_refuses_when_the_source_cannot_be_sized(tmp_path, monkeypatch):
    """A source whose size cannot be read used to reserve ZERO, which is more
    permissive than any real disk. Refuse instead."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: 1 << 40)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)

    def _boom(path):
        raise OSError("stat failed")

    monkeypatch.setattr(task, "os_stat", _boom)

    with pytest.raises(RuntimeError) as excinfo:
        task.move(src, dst, "rsync", min_free_bytes=8192, remove_source_file=False)

    assert "cannot size" in str(excinfo.value)
    assert not Path(dst).exists()


def test_an_unknown_method_is_rejected_before_the_floor_is_probed(
    tmp_path, monkeypatch
):
    """Order matters: the floor runs early, so without an explicit method check
    ahead of it a caller error (``method="teleport"``) surfaces as "cannot read
    the free space" and points at the filesystem instead of at the call."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    probed = []
    monkeypatch.setattr(task, "_free_space", lambda p: probed.append(p) or None)

    with pytest.raises(ValueError) as excinfo:
        task.move(src, dst, "teleport", min_free_bytes=8192)

    assert "Invalid move method" in str(excinfo.value)
    assert probed == []  # the filesystem was never touched


def test_a_same_filesystem_move_is_still_never_blocked(tmp_path, monkeypatch):
    """A rename consumes nothing, so no probe failure may refuse it. This must
    keep holding after the gate turns fail-closed."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "dst.qcow2")  # same tmp_path -> same st_dev
    monkeypatch.setattr(task, "_free_space", lambda p: None)

    task.move(src, dst, "auto", min_free_bytes=1 << 40)

    assert Path(dst).exists()
    assert not Path(src).exists()


def test_move_floor_can_be_switched_off_explicitly(tmp_path, monkeypatch):
    """``min_free_bytes=0`` is an operator saying "no floor". It must still mean
    that after the default becomes non-zero, or there is no way back."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: None)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)

    task.move(src, dst, "rsync", min_free_bytes=0, remove_source_file=False)


def test_move_applies_the_default_floor_when_none_is_given(tmp_path, monkeypatch):
    """A caller that passes no floor used to get NO protection. It now gets the
    default one, which is the whole point of a default."""
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "DEFAULT_MIN_FREE_BYTES", 1 << 30)
    monkeypatch.setattr(task, "_free_space", lambda p: 4096)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)

    with pytest.raises(RuntimeError) as excinfo:
        task.move(src, dst, "rsync", remove_source_file=False)

    assert "refusing to copy" in str(excinfo.value)


# --------------------------------------------------------------------------
# convert and disconnect: a floor where there was none
# --------------------------------------------------------------------------


def test_convert_refuses_when_the_destination_would_breach_the_floor(
    tmp_path, monkeypatch
):
    src = _sized(tmp_path, "src.qcow2", 5000)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: 10000)
    monkeypatch.setattr(task, "_qemu_measure_required", lambda s, o: 5000)
    called = {}
    monkeypatch.setattr(
        task, "run_with_progress", lambda *a, **k: called.setdefault("ran", True) or 0
    )

    with pytest.raises(RuntimeError) as excinfo:
        task.convert(src, dst, "qcow2", False, min_free_bytes=8000, **_GEO)

    assert "would be left" in str(excinfo.value)  # the breach path, not a measure error
    assert "ran" not in called  # qemu-img was never started
    assert not Path(dst).exists()


def test_convert_refuses_when_free_space_is_unknown(tmp_path, monkeypatch):
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: None)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)

    with pytest.raises(RuntimeError) as excinfo:
        task.convert(src, dst, "qcow2", False, min_free_bytes=8192, **_GEO)

    assert "cannot read the free space" in str(excinfo.value)


def test_convert_proceeds_when_there_is_room(tmp_path, monkeypatch):
    src = _sized(tmp_path, "src.qcow2", 1024)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_free_space", lambda p: 1 << 40)
    monkeypatch.setattr(task, "_qemu_measure_required", lambda s, o: 1024)
    called = {}

    def _ran(*a, **k):
        called["ran"] = True
        return 0

    monkeypatch.setattr(task, "run_with_progress", _ran)

    assert task.convert(src, dst, "qcow2", False, min_free_bytes=8192, **_GEO) == 0
    assert called.get("ran") is True


def test_disconnect_refuses_when_the_sibling_would_breach_the_floor(
    tmp_path, monkeypatch
):
    """``disconnect`` writes a ``.wo_chain`` sibling in the SAME directory, so
    the disk it can fill is the one holding the live disk."""
    disk = _sized(tmp_path, "disk.qcow2", 5000)
    monkeypatch.setattr(task, "_free_space", lambda p: 10000)
    monkeypatch.setattr(task, "_qemu_measure_required", lambda s, o: 5000)
    called = {}
    monkeypatch.setattr(task, "run", lambda *a, **k: called.setdefault("ran", True))

    with pytest.raises(RuntimeError) as excinfo:
        task.disconnect(disk, min_free_bytes=8000, **_GEO)

    assert "refusing to disconnect" in str(excinfo.value)
    assert "ran" not in called
    assert not Path(disk + ".wo_chain").exists()
    assert Path(disk).exists()  # the live disk is untouched


def test_disconnect_refuses_when_free_space_is_unknown(tmp_path, monkeypatch):
    disk = _sized(tmp_path, "disk.qcow2", 1024)
    monkeypatch.setattr(task, "_free_space", lambda p: None)
    monkeypatch.setattr(task, "run", lambda *a, **k: None)

    with pytest.raises(RuntimeError) as excinfo:
        task.disconnect(disk, min_free_bytes=8192, **_GEO)

    assert "cannot read the free space" in str(excinfo.value)


def test_disconnect_measures_after_clearing_a_stale_sibling(tmp_path, monkeypatch):
    """A crashed prior run leaves a ``.wo_chain`` holding a whole disk image on
    the very filesystem being measured. It must be unlinked BEFORE the probe, or
    the floor refuses on space that is about to be released."""
    disk = _sized(tmp_path, "disk.qcow2", 1024)
    stale = Path(disk + ".wo_chain")
    stale.write_bytes(b"\0" * 4096)
    seen = {}

    def _free(path):
        seen["stale_gone"] = not stale.exists()
        return 1 << 40

    monkeypatch.setattr(task, "_free_space", _free)
    monkeypatch.setattr(task, "_qemu_measure_required", lambda s, o: 1024)
    monkeypatch.setattr(task, "run", lambda *a, **k: stale.write_bytes(b"\0" * 8))

    task.disconnect(disk, min_free_bytes=8192, **_GEO)

    assert seen["stale_gone"] is True


# --------------------------------------------------------------------------
# The gate reserves qemu-img measure's ``required`` for the exact option string,
# not the virtual size: preallocation=metadata stays sparse.
# --------------------------------------------------------------------------


def _measure_by_options(mapping):
    """Return a fake ``_qemu_measure_required`` that answers by the options seen,
    and records every call so the option string can be asserted."""
    seen = []

    def _fake(source_path, options, source_format=None):
        seen.append(options)
        for needle, value in mapping.items():
            if needle in options:
                return value
        return mapping.get("_default")

    _fake.seen = seen
    return _fake


def test_off_preallocation_skips_the_measure_and_uses_apparent_size(
    tmp_path, monkeypatch
):
    """preallocation=off (the default/recommended) writes a sparse destination,
    so the cheap os_stat proxy is enough -- the expensive metadata walk of
    qemu-img measure must NOT run in the common path."""
    src = _sized(tmp_path, "src.qcow2", 5000)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_physical_free_space", lambda p: None)
    monkeypatch.setattr(task, "_free_space", lambda p: 50_000)
    measured = {}

    def _measure(*a, **k):
        measured["ran"] = True
        return 1000

    monkeypatch.setattr(task, "_qemu_measure_required", _measure)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)
    geo = {**_GEO, "preallocation": "off"}
    assert task.convert(src, dst, "qcow2", False, min_free_bytes=8192, **geo) == 0
    assert "ran" not in measured  # off never measures


def test_disconnect_off_preallocation_skips_the_measure(tmp_path, monkeypatch):
    disk = _sized(tmp_path, "disk.qcow2", 5000)
    monkeypatch.setattr(task, "_physical_free_space", lambda p: None)
    monkeypatch.setattr(task, "_free_space", lambda p: 50_000)
    measured = {}
    monkeypatch.setattr(
        task,
        "_qemu_measure_required",
        lambda *a, **k: measured.setdefault("ran", True) or 1000,
    )
    monkeypatch.setattr(task, "run", lambda *a, **k: None)
    monkeypatch.setattr(task, "rename", lambda a, b: None)
    geo = {**_GEO, "preallocation": "off"}
    assert task.disconnect(disk, min_free_bytes=8192, **geo) == 0
    assert "ran" not in measured


def test_measure_has_its_own_timeout_larger_than_header_reads():
    # A full-image metadata walk is bounded work but far slower than a header
    # read, so it must not share the 30 s QEMU_IMG_TIMEOUT.
    assert task.QEMU_MEASURE_TIMEOUT > task.QEMU_IMG_TIMEOUT


def test_disconnect_measure_forces_the_qcow2_source_format(tmp_path, monkeypatch):
    """disconnect's source is always a qcow2 disk it controls, so its measure
    must pin -f qcow2 rather than probe a guest-writable file's header."""
    disk = _sized(tmp_path, "disk.qcow2", 5000)
    monkeypatch.setattr(task, "_physical_free_space", lambda p: None)
    monkeypatch.setattr(task, "_free_space", lambda p: 1 << 40)
    seen = {}

    def _measure(source_path, options, source_format=None):
        seen["source_format"] = source_format
        return 1000

    monkeypatch.setattr(task, "_qemu_measure_required", _measure)
    monkeypatch.setattr(task, "run", lambda *a, **k: None)
    monkeypatch.setattr(task, "rename", lambda a, b: None)
    geo = {**_GEO, "preallocation": "full"}
    task.disconnect(disk, min_free_bytes=8192, **geo)
    assert seen["source_format"] == "qcow2"


def test_convert_full_preallocation_reserves_the_measured_required(
    tmp_path, monkeypatch
):
    src = _sized(tmp_path, "src.qcow2", 5000)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_physical_free_space", lambda p: None)
    monkeypatch.setattr(task, "_free_space", lambda p: 50_000)
    monkeypatch.setattr(
        task, "_qemu_measure_required", _measure_by_options({"full": 1 << 40})
    )
    ran = {}
    monkeypatch.setattr(
        task, "run_with_progress", lambda *a, **k: ran.setdefault("ran", True) or 0
    )
    geo = {**_GEO, "preallocation": "full"}
    with pytest.raises(RuntimeError, match="refusing to convert"):
        task.convert(src, dst, "qcow2", False, min_free_bytes=8192, **geo)
    assert "ran" not in ran


def test_convert_metadata_reserves_the_measured_required_not_the_virtual_size(
    tmp_path, monkeypatch
):
    """metadata stays sparse, so measure returns a small required. Free sits just
    above it and far below the virtual size, so the test fails if the gate ever
    reverts to reserving virtual."""
    src = _sized(tmp_path, "src.qcow2", 5000)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_physical_free_space", lambda p: None)
    monkeypatch.setattr(task, "_free_space", lambda p: 5_500_000)
    monkeypatch.setattr(task, "_qemu_measure_required", lambda s, o, f=None: 3_500_000)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)
    geo = {**_GEO, "preallocation": "metadata"}
    assert task.convert(src, dst, "qcow2", False, min_free_bytes=1_000_000, **geo) == 0


def test_disconnect_metadata_reserves_the_measured_required(tmp_path, monkeypatch):
    disk = _sized(tmp_path, "disk.qcow2", 5000)
    monkeypatch.setattr(task, "_physical_free_space", lambda p: None)
    monkeypatch.setattr(task, "_free_space", lambda p: 5_500_000)
    monkeypatch.setattr(task, "_qemu_measure_required", lambda s, o, f=None: 3_500_000)
    monkeypatch.setattr(task, "run", lambda *a, **k: None)
    monkeypatch.setattr(task, "rename", lambda a, b: None)
    geo = {**_GEO, "preallocation": "metadata"}
    assert task.disconnect(disk, min_free_bytes=1_000_000, **geo) == 0


def test_disconnect_full_preallocation_is_refused_when_it_would_breach(
    tmp_path, monkeypatch
):
    disk = _sized(tmp_path, "disk.qcow2", 5000)
    monkeypatch.setattr(task, "_physical_free_space", lambda p: None)
    monkeypatch.setattr(task, "_free_space", lambda p: 50_000)
    monkeypatch.setattr(task, "_qemu_measure_required", lambda s, o, f=None: 1 << 40)
    ran = {}
    monkeypatch.setattr(task, "run", lambda *a, **k: ran.setdefault("ran", True))
    geo = {**_GEO, "preallocation": "full"}
    with pytest.raises(RuntimeError, match="refusing to disconnect"):
        task.disconnect(disk, min_free_bytes=8192, **geo)
    assert "ran" not in ran
    assert Path(disk).exists()


def test_gate_measures_with_the_exact_write_option_string(tmp_path, monkeypatch):
    """The measure must use the SAME -o string the write uses -- including the
    preallocation term, so the reserved footprint matches what qemu-img writes."""
    src = _sized(tmp_path, "src.qcow2", 5000)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_physical_free_space", lambda p: None)
    monkeypatch.setattr(task, "_free_space", lambda p: 1 << 40)
    fake = _measure_by_options({"_default": 1000})
    monkeypatch.setattr(task, "_qemu_measure_required", fake)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)
    geo = {**_GEO, "preallocation": "metadata"}
    task.convert(src, dst, "qcow2", False, min_free_bytes=8192, **geo)
    assert fake.seen, "a preallocating convert must measure the destination"
    assert "preallocation=metadata" in fake.seen[0]


def test_convert_fails_closed_when_measure_fails(tmp_path, monkeypatch):
    src = _sized(tmp_path, "src.qcow2", 5000)
    dst = str(tmp_path / "out" / "dst.qcow2")
    monkeypatch.setattr(task, "_physical_free_space", lambda p: None)
    monkeypatch.setattr(task, "_free_space", lambda p: 1 << 40)  # plenty
    monkeypatch.setattr(task, "_qemu_measure_required", lambda s, o, f=None: None)
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)
    geo = {**_GEO, "preallocation": "full"}
    with pytest.raises(RuntimeError, match="measure"):
        task.convert(src, dst, "qcow2", False, min_free_bytes=8192, **geo)


def test_vmdk_destination_convert_uses_apparent_size(tmp_path, monkeypatch):
    """A vmdk destination takes no -o and no qcow2 measure; it must not fail
    closed on the measure path."""
    src = _sized(tmp_path, "src.qcow2", 5000)
    dst = str(tmp_path / "out" / "dst.vmdk")
    monkeypatch.setattr(task, "_physical_free_space", lambda p: None)
    monkeypatch.setattr(task, "_free_space", lambda p: 50_000)
    monkeypatch.setattr(
        task,
        "_qemu_measure_required",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not measure a vmdk")
        ),
    )
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 0)
    assert task.convert(src, dst, "vmdk", False, min_free_bytes=8192, **_GEO) == 0


# --------------------------------------------------------------------------
# _qemu_measure_required: direct coverage (previously monkeypatched away)
# --------------------------------------------------------------------------


class _Measured:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_qemu_measure_required_probes_the_source_without_forcing_qcow2(monkeypatch):
    """It must NOT pin -f qcow2 on the source, or a vmdk->qcow2 convert measures
    a vmdk as qcow2, fails, and the gate refuses a perfectly runnable convert."""
    calls = []
    monkeypatch.setattr(
        task,
        "run",
        lambda cmd, **k: calls.append(cmd) or _Measured(stdout=b'{"required": 4096}'),
    )
    got = task._qemu_measure_required("/isard/g/d.vmdk", "cluster_size=64k")
    assert got == 4096
    cmd = calls[0]
    assert cmd[:2] == ["qemu-img", "measure"]
    assert "-O" in cmd and cmd[cmd.index("-O") + 1] == "qcow2"
    assert "-f" not in cmd  # the SOURCE format is probed, not forced


def test_qemu_measure_required_forces_the_source_format_when_given(monkeypatch):
    calls = []
    monkeypatch.setattr(
        task,
        "run",
        lambda cmd, **k: calls.append(cmd) or _Measured(stdout=b'{"required": 8}'),
    )
    task._qemu_measure_required("/isard/g/d.qcow2", "cluster_size=64k", "qcow2")
    cmd = calls[0]
    assert "-f" in cmd and cmd[cmd.index("-f") + 1] == "qcow2"


def test_qemu_measure_required_uses_its_own_timeout(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        task,
        "run",
        lambda cmd, **k: seen.update(k) or _Measured(stdout=b'{"required": 8}'),
    )
    task._qemu_measure_required("/isard/g/d.qcow2", "cluster_size=64k")
    assert seen["timeout"] == task.QEMU_MEASURE_TIMEOUT


def test_qemu_measure_required_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(task, "run", lambda cmd, **k: _Measured(returncode=1))
    assert task._qemu_measure_required("/isard/g/d.qcow2", "cluster_size=64k") is None


def test_qemu_measure_required_returns_none_on_timeout(monkeypatch):
    def _boom(cmd, **k):
        raise task.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(task, "run", _boom)
    assert task._qemu_measure_required("/isard/g/d.qcow2", "cluster_size=64k") is None


def test_qemu_measure_required_returns_none_on_unparseable_output(monkeypatch):
    monkeypatch.setattr(
        task, "run", lambda cmd, **k: _Measured(stdout=b"not json at all")
    )
    assert task._qemu_measure_required("/isard/g/d.qcow2", "cluster_size=64k") is None
