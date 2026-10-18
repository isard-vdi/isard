# SPDX-License-Identifier: AGPL-3.0-or-later

"""scan_backing_index: the read-only header walk the integrity pass reads back."""

from isardvdi_storage import task


def test_it_collects_qcow2_recursively_and_skips_the_rest(tmp_path):
    (tmp_path / "a.qcow2").write_bytes(b"not-a-real-qcow2")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.qcow2").write_bytes(b"x")
    (tmp_path / ".hidden.qcow2").write_bytes(b"x")  # dotfile: skipped
    (tmp_path / "c.txt").write_bytes(b"x")  # not a qcow2: skipped

    res = task.scan_backing_index([str(tmp_path)])

    assert res["scanned"] == 2
    assert set(res["index"]) == {str(tmp_path / "a.qcow2"), str(sub / "b.qcow2")}
    # a non-qcow2 body is indexed but marked unreadable, never read as "no backing"
    assert res["index"][str(tmp_path / "a.qcow2")]["readable"] is False


def test_an_empty_pool_scans_clean(tmp_path):
    res = task.scan_backing_index([str(tmp_path)])
    assert res["scanned"] == 0
    assert res["index"] == {}
