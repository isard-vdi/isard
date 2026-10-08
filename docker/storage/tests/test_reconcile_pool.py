# SPDX-License-Identifier: AGPL-3.0-or-later

"""reconcile_pool scans, classifies, writes metrics and re-measures only with apply."""

from isardvdi_storage.task import reconcile_pool


def _write(path, nbytes):
    path.write_bytes(b"\0" * nbytes)
    return str(path)


def test_reports_drift_and_orphan_without_applying(tmp_path):
    drifted = _write(tmp_path / "a.qcow2", 8192)
    _write(tmp_path / "orphan.qcow2", 8192)
    storages = [
        {
            "id": "a",
            "status": "ready",
            "path": drifted,
            "qemu-img-info": {"actual-size": 0, "virtual-size": 1 << 30},
        },
    ]
    refreshed = []
    report = reconcile_pool(
        str(tmp_path),
        threshold=1024,
        apply=False,
        metrics_file=str(tmp_path / "m.prom"),
        _fetch_storages=lambda: storages,
        _fetch_medias=lambda: [],
        _refresh=lambda ids: refreshed.append(list(ids)),
    )
    assert report["applied"] is False
    assert report["corrected"] == []
    assert refreshed == []  # report-only: never re-measured
    assert report["metrics"]["size_drift_files"] == 1
    assert report["metrics"]["file_without_row_files"] == 1
    # metrics textfile written in the node_exporter format
    text = (tmp_path / "m.prom").read_text()
    assert 'isardvdi_storage_reconcile{pool="' in text
    assert 'class="size_drift_files"} 1' in text


def test_apply_re_measures_ready_drift_through_the_injected_refresh(tmp_path):
    drifted = _write(tmp_path / "a.qcow2", 8192)
    storages = [
        {
            "id": "a",
            "status": "ready",
            "path": drifted,
            "qemu-img-info": {"actual-size": 0, "virtual-size": 1 << 30},
        },
    ]
    refreshed = []
    report = reconcile_pool(
        str(tmp_path),
        threshold=1024,
        apply=True,
        _fetch_storages=lambda: storages,
        _fetch_medias=lambda: [],
        _refresh=lambda ids: refreshed.append(list(ids)),
    )
    assert report["applied"] is True
    assert report["corrected"] == ["a"]
    assert refreshed == [["a"]]


def test_media_drift_is_reported_but_never_re_measured(tmp_path):
    iso = _write(tmp_path / "m.iso", 8192)
    medias = [
        {
            "id": "m",
            "status": "Downloaded",
            "path_downloaded": iso,
            "progress": {"total_bytes": 0},
        }
    ]
    refreshed = []
    report = reconcile_pool(
        str(tmp_path),
        threshold=1024,
        apply=True,
        _fetch_storages=lambda: [],
        _fetch_medias=lambda: medias,
        _refresh=lambda ids: refreshed.append(list(ids)),
    )
    assert report["metrics"]["size_drift_files"] == 1  # media drift is classified
    assert report["corrected"] == []  # but storage-only re-measure
    assert refreshed == []


def test_budget_stops_the_scan_early(tmp_path):
    for i in range(5):
        _write(tmp_path / f"f{i}.qcow2", 4096)
    report = reconcile_pool(
        str(tmp_path),
        max_files=2,
        apply=False,
        _fetch_storages=lambda: [],
        _fetch_medias=lambda: [],
    )
    assert report["budget_hit"] is True
