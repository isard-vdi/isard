# SPDX-License-Identifier: AGPL-3.0-or-later

"""The header reader must match qemu-img, and refuse what it does not understand."""

import json
import shutil
import struct
import subprocess

import pytest
from storage_lib import qcow, qcow_header
from storage_lib.qcow_header import Qcow2HeaderError, backing_file, read_header


def make_qcow2(
    path, version=3, backing=None, fmt=None, cluster_bits=16, incompatible=0
):
    """Write a minimal qcow2 header laid out the way qemu-img create does."""
    header_length = 72 if version == 2 else 104
    ext = b""
    if fmt is not None:
        raw = fmt.encode()
        ext += struct.pack(">II", qcow_header.EXT_BACKING_FORMAT, len(raw))
        ext += raw.ljust((len(raw) + 7) & ~7, b"\0")
    ext += struct.pack(">II", 0, 0)
    name = backing.encode() if backing is not None else b""
    backing_offset = header_length + len(ext) if backing is not None else 0
    head = b"QFI\xfb" + struct.pack(
        ">IQIIQIIQQIIQ",
        version,
        backing_offset,
        len(name),
        cluster_bits,
        1 << 30,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    if version == 3:
        head += struct.pack(">QQQII", incompatible, 0, 0, 4, header_length)
    data = head + ext + name
    path.write_bytes(data.ljust(1 << cluster_bits, b"\0"))
    return path


class TestReadHeader:
    def test_no_backing_is_none(self, tmp_path):
        img = make_qcow2(tmp_path / "base.qcow2")
        assert backing_file(img) is None

    def test_absolute_backing_is_returned_as_is(self, tmp_path):
        img = make_qcow2(tmp_path / "c.qcow2", backing="/pool/base.qcow2")
        assert backing_file(img) == "/pool/base.qcow2"

    def test_relative_backing_resolves_against_the_image_dir(self, tmp_path):
        img = make_qcow2(tmp_path / "c.qcow2", backing="../t/base.qcow2")
        assert backing_file(img) == f"{tmp_path}/../t/base.qcow2"

    def test_protocol_backing_is_not_resolved(self, tmp_path):
        img = make_qcow2(tmp_path / "c.qcow2", backing="nbd:host:10809")
        assert backing_file(img) == "nbd:host:10809"

    def test_backing_with_spaces(self, tmp_path):
        img = make_qcow2(tmp_path / "c.qcow2", backing="/pool/my base.qcow2")
        assert backing_file(img) == "/pool/my base.qcow2"

    def test_v2_header(self, tmp_path):
        img = make_qcow2(tmp_path / "c.qcow2", version=2, backing="/p/b.qcow2")
        assert read_header(img) == (2, "/p/b.qcow2", None)

    def test_backing_format_extension(self, tmp_path):
        img = make_qcow2(tmp_path / "c.qcow2", backing="/p/b.qcow2", fmt="qcow2")
        assert read_header(img) == (3, "/p/b.qcow2", "qcow2")

    def test_empty_file_is_rejected(self, tmp_path):
        img = tmp_path / "e.qcow2"
        img.write_bytes(b"")
        with pytest.raises(Qcow2HeaderError):
            backing_file(img)

    def test_raw_file_is_rejected(self, tmp_path):
        img = tmp_path / "r.qcow2"
        img.write_bytes(b"\0" * 4096)
        with pytest.raises(Qcow2HeaderError):
            backing_file(img)

    def test_truncated_header_is_rejected(self, tmp_path):
        img = make_qcow2(tmp_path / "c.qcow2", backing="/p/b.qcow2")
        img.write_bytes(img.read_bytes()[:80])
        with pytest.raises(Qcow2HeaderError):
            backing_file(img)

    def test_truncated_backing_name_is_rejected(self, tmp_path):
        img = make_qcow2(tmp_path / "c.qcow2", backing="/p/b.qcow2")
        img.write_bytes(img.read_bytes()[: 104 + 8 + 4])
        with pytest.raises(Qcow2HeaderError):
            backing_file(img)

    @pytest.mark.parametrize("version", [1, 4])
    def test_unsupported_version_is_rejected(self, tmp_path, version):
        img = make_qcow2(tmp_path / "c.qcow2")
        data = bytearray(img.read_bytes())
        data[4:8] = struct.pack(">I", version)
        img.write_bytes(bytes(data))
        with pytest.raises(Qcow2HeaderError):
            backing_file(img)

    def test_unknown_incompatible_feature_is_rejected(self, tmp_path):
        img = make_qcow2(
            tmp_path / "c.qcow2", backing="/p/b.qcow2", incompatible=1 << 5
        )
        with pytest.raises(Qcow2HeaderError):
            backing_file(img)

    def test_backing_name_outside_first_cluster_is_rejected(self, tmp_path):
        img = make_qcow2(tmp_path / "c.qcow2", backing="/p/b.qcow2", cluster_bits=9)
        data = bytearray(img.read_bytes())
        data[8:16] = struct.pack(">Q", 510)
        img.write_bytes(bytes(data))
        with pytest.raises(Qcow2HeaderError):
            backing_file(img)


class TestFallback:
    def test_valid_header_does_not_run_qemu_img(self, tmp_path, monkeypatch):
        img = make_qcow2(tmp_path / "c.qcow2", backing="/p/b.qcow2")
        monkeypatch.setattr(
            qcow, "qemu_img_info", lambda p: pytest.fail("qemu-img was run")
        )
        assert qcow.read_backing_file(str(img)) == "/p/b.qcow2"

    def test_unreadable_header_asks_qemu_img(self, tmp_path, monkeypatch):
        img = tmp_path / "r.qcow2"
        img.write_bytes(b"\0" * 4096)
        asked = []
        monkeypatch.setattr(
            qcow,
            "qemu_img_info",
            lambda p: asked.append(p) or {"full-backing-filename": "/q/b.qcow2"},
        )
        assert qcow.read_backing_file(str(img)) == "/q/b.qcow2"
        assert asked == [str(img)]

    def test_missing_file_asks_qemu_img(self, tmp_path, monkeypatch):
        monkeypatch.setattr(qcow, "qemu_img_info", lambda p: None)
        assert qcow.read_backing_file(str(tmp_path / "gone.qcow2")) is None

    def test_analyze_dependencies_reads_headers(self, tmp_path, monkeypatch):
        base = make_qcow2(tmp_path / "base.qcow2")
        a = make_qcow2(tmp_path / "a.qcow2", backing=str(base))
        b = make_qcow2(tmp_path / "b.qcow2", backing="base.qcow2")
        monkeypatch.setattr(
            qcow, "qemu_img_info", lambda p: pytest.fail("qemu-img was run")
        )
        files = [str(base), str(a), str(b)]

        deps = qcow.analyze_dependencies(files)

        assert deps["reverse_map"] == {str(base): [str(a), str(b)]}
        assert deps["wo_backing"] == [str(base)]
        assert deps["wo_derivatives"] == [str(a), str(b)]


QEMU_IMG = shutil.which("qemu-img")


def qemu_backing(path):
    out = subprocess.run(
        ["qemu-img", "info", "-U", "--output=json", str(path)],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return "ERROR"
    info = json.loads(out.stdout)
    return info.get("full-backing-filename") or info.get("backing-filename")


def create(path, *opts, size=None):
    size = [size] if size else []
    subprocess.run(
        ["qemu-img", "create", "-q", "-f", "qcow2", *opts, str(path), *size],
        check=True,
    )
    return path


def without_backing_format(path):
    """Older images carry no backing format; qemu-img no longer writes such."""
    data = bytearray(path.read_bytes())
    at = data.index(struct.pack(">I", qcow_header.EXT_BACKING_FORMAT))
    data[at : at + 4] = struct.pack(">I", 0x12345678)
    path.write_bytes(bytes(data))
    return path


@pytest.mark.skipif(QEMU_IMG is None, reason="needs qemu-img")
class TestParityWithQemuImg:
    @pytest.fixture
    def pool(self, tmp_path):
        base_dir = tmp_path / "base dir"
        base_dir.mkdir()
        (tmp_path / "child").mkdir()
        base = create(base_dir / "base.qcow2", size="1M")
        create(base_dir / "base v2.qcow2", "-o", "compat=0.10", size="1M")
        return tmp_path, base

    def cases(self, pool):
        tmp_path, base = pool
        child = tmp_path / "child"
        return [
            base,
            tmp_path / "base dir" / "base v2.qcow2",
            create(child / "abs.qcow2", "-F", "qcow2", "-b", str(base)),
            create(child / "rel.qcow2", "-F", "qcow2", "-b", "../base dir/base.qcow2"),
            create(
                child / "v2.qcow2",
                "-o",
                "compat=0.10",
                "-F",
                "qcow2",
                "-b",
                str(base),
            ),
            without_backing_format(
                create(child / "nofmt.qcow2", "-F", "qcow2", "-b", str(base))
            ),
            create(child / "grandchild.qcow2", "-F", "qcow2", "-b", "rel.qcow2"),
        ]

    def test_same_backing_as_qemu_img(self, pool):
        for img in self.cases(pool):
            assert backing_file(img) == qemu_backing(img), img

    def test_formats_as_qemu_img_wrote_them(self, pool):
        tmp_path, base = pool
        child = tmp_path / "child"
        with_fmt = create(child / "f.qcow2", "-F", "qcow2", "-b", str(base))
        without = without_backing_format(
            create(child / "n.qcow2", "-F", "qcow2", "-b", str(base))
        )
        v2 = create(
            child / "v2f.qcow2", "-o", "compat=0.10", "-F", "qcow2", "-b", str(base)
        )
        assert read_header(with_fmt) == (3, str(base), "qcow2")
        assert read_header(without) == (3, str(base), None)
        assert read_header(v2) == (2, str(base), "qcow2")

    def test_what_it_refuses_qemu_img_reads_as_no_backing(self, tmp_path):
        raw = tmp_path / "raw.qcow2"
        subprocess.run(
            ["qemu-img", "create", "-q", "-f", "raw", str(raw), "1M"], check=True
        )
        empty = tmp_path / "empty.qcow2"
        empty.write_bytes(b"")
        truncated = create(tmp_path / "t.qcow2", size="1M")
        truncated.write_bytes(truncated.read_bytes()[:50])
        for img in (raw, empty, truncated):
            with pytest.raises(Qcow2HeaderError):
                backing_file(img)
            assert qcow.read_backing_file(str(img)) == qcow.get_backing_file(str(img))
            assert qcow.get_backing_file(str(img)) is None
