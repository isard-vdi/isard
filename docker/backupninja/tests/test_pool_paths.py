"""Unit tests for ``pool_paths``; they must not import the generated apiv4 client."""

import os

from isardvdi_backupninja import pool_paths

# Pure: map / filter


def test_map_prefixes_keeps_only_pool_root_and_maps_isard_to_opt():
    got = pool_paths.map_prefixes(
        [
            "/isard/storage_pools/fast/catA/templates",
            "/isard/storage_pools/slow/catB/desktops",
        ]
    )
    assert got == [
        "/opt/isard/storage_pools/fast/catA/templates",
        "/opt/isard/storage_pools/slow/catB/desktops",
    ]


def test_map_prefixes_drops_non_pool_paths():
    # Standard disk locations are backed up by the disks jobs, never pools.
    got = pool_paths.map_prefixes(
        [
            "/isard/templates/catA/x",
            "/isard/groups/catA/u/y",
            "/isard/media/z",
            "/isard/storage_pools/p/catA/templates",
            "/some/other/place",
        ]
    )
    assert got == ["/opt/isard/storage_pools/p/catA/templates"]


def test_map_prefixes_dedups_and_sorts_and_normalizes_trailing_slash():
    got = pool_paths.map_prefixes(
        [
            "/isard/storage_pools/p/catA/templates/",
            "/isard/storage_pools/p/catA/templates",
            "/isard/storage_pools/a/catA/templates",
        ]
    )
    assert got == [
        "/opt/isard/storage_pools/a/catA/templates",
        "/opt/isard/storage_pools/p/catA/templates",
    ]


def test_map_prefixes_ignores_blank_and_root_only():
    got = pool_paths.map_prefixes(["", "  ", "/isard/storage_pools"])
    assert got == []


# Pure: excludes


def test_parse_excludes_default_is_volatile():
    assert pool_paths.parse_excludes(None) == ["*/volatile*"]


def test_parse_excludes_splits_on_comma_and_whitespace():
    assert pool_paths.parse_excludes("*/volatile*, */scratch*  */tmp*") == [
        "*/volatile*",
        "*/scratch*",
        "*/tmp*",
    ]


def test_parse_excludes_empty_string_means_no_excludes():
    assert pool_paths.parse_excludes("") == []


def test_apply_excludes_default_volatile():
    paths = [
        "/opt/isard/storage_pools/p/catA/templates",
        "/opt/isard/storage_pools/p/catA/volatile",
        "/opt/isard/storage_pools/p/fast/catA/volatile",
    ]
    assert pool_paths.apply_excludes(paths, ["*/volatile*"]) == [
        "/opt/isard/storage_pools/p/catA/templates",
    ]


def test_apply_excludes_no_patterns_keeps_all():
    paths = ["/opt/isard/storage_pools/p/catA/volatile"]
    assert pool_paths.apply_excludes(paths, []) == paths


# Pure: containment


def test_drop_contained_drops_descendant_keeps_ancestor():
    paths = [
        "/opt/isard/storage_pools/p/fast",
        "/opt/isard/storage_pools/p/fast/catA/templates",
        "/opt/isard/storage_pools/p/slow",
    ]
    assert pool_paths.drop_contained(paths) == [
        "/opt/isard/storage_pools/p/fast",
        "/opt/isard/storage_pools/p/slow",
    ]


def test_drop_contained_keeps_siblings_and_prefix_lookalikes():
    # ".../fast" must NOT be treated as an ancestor of ".../fastlane".
    paths = [
        "/opt/isard/storage_pools/p/fast",
        "/opt/isard/storage_pools/p/fastlane",
    ]
    assert pool_paths.drop_contained(paths) == paths


# FS: has_regular_file


def test_has_regular_file_true_when_file_present(tmp_path):
    d = tmp_path / "pool"
    (d / "sub").mkdir(parents=True)
    (d / "sub" / "disk.qcow2").write_bytes(b"x")
    assert pool_paths.has_regular_file(str(d)) is True


def test_has_regular_file_false_for_empty_dir(tmp_path):
    d = tmp_path / "emptypool"
    d.mkdir()
    assert pool_paths.has_regular_file(str(d)) is False


# FS: inode dedupe (symlinked dir stands in for a bind mount)


def test_dedupe_by_inode_collapses_symlinked_duplicate(tmp_path):
    real = tmp_path / "storage_pools" / "poolA"
    real.mkdir(parents=True)
    (real / "disk.qcow2").write_bytes(b"x")
    dup = tmp_path / "storage_pools" / "poolA_alias"
    os.symlink(str(real), str(dup))  # os.stat follows -> same (st_dev, st_ino)

    kept = pool_paths.dedupe_by_inode([str(dup), str(real)])
    # Exactly one survivor, and it is the shortest real path.
    assert kept == [str(real)]


def test_dedupe_by_inode_keeps_distinct_dirs(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    kept = pool_paths.dedupe_by_inode([str(b), str(a)])
    assert kept == [str(a), str(b)]


# resolve(): full pipeline given already-fetched prefixes


def _make_pool_tree(tmp_path):
    """Build a realistic mapped tree and return (host_root, prefixes)."""
    host_root = tmp_path / "opt_isard"
    sp = host_root / "storage_pools"
    # a good pool dir with a disk
    (sp / "p" / "fast" / "catA" / "templates").mkdir(parents=True)
    (sp / "p" / "fast" / "catA" / "templates" / "d.qcow2").write_bytes(b"x")
    # a volatile dir (to be excluded)
    (sp / "p" / "fast" / "catA" / "volatile").mkdir(parents=True)
    (sp / "p" / "fast" / "catA" / "volatile" / "v.qcow2").write_bytes(b"x")
    # an empty (unmounted-like) pool dir
    (sp / "q" / "slow" / "catB" / "templates").mkdir(parents=True)
    return host_root, sp


def test_resolve_happy_path_excludes_volatile(tmp_path, monkeypatch):
    host_root, sp = _make_pool_tree(tmp_path)
    monkeypatch.setattr(pool_paths, "HOST_ROOT", str(host_root))
    prefixes = [
        "/isard/storage_pools/p/fast/catA/templates",
        "/isard/storage_pools/p/fast/catA/volatile",
    ]
    result = pool_paths.resolve(prefixes, excludes=["*/volatile*"])
    assert result.kept == [str(sp / "p" / "fast" / "catA" / "templates")]
    assert result.missing == []


def test_resolve_flags_empty_dir_as_missing(tmp_path, monkeypatch):
    host_root, sp = _make_pool_tree(tmp_path)
    monkeypatch.setattr(pool_paths, "HOST_ROOT", str(host_root))
    prefixes = ["/isard/storage_pools/q/slow/catB/templates"]
    result = pool_paths.resolve(prefixes, excludes=["*/volatile*"])
    assert result.kept == []
    assert [p for p, _ in result.missing] == [
        str(sp / "q" / "slow" / "catB" / "templates")
    ]


def test_resolve_flags_absent_dir_as_missing(tmp_path, monkeypatch):
    host_root, sp = _make_pool_tree(tmp_path)
    monkeypatch.setattr(pool_paths, "HOST_ROOT", str(host_root))
    prefixes = ["/isard/storage_pools/does/not/exist"]
    result = pool_paths.resolve(prefixes, excludes=["*/volatile*"])
    assert result.kept == []
    assert len(result.missing) == 1


# CLI: main()


def test_main_default_prints_kept_dirs(tmp_path, monkeypatch, capsys):
    host_root, sp = _make_pool_tree(tmp_path)
    monkeypatch.setattr(pool_paths, "HOST_ROOT", str(host_root))
    monkeypatch.setattr(
        pool_paths,
        "fetch_prefixes",
        lambda *a, **k: ["/isard/storage_pools/p/fast/catA/templates"],
    )
    monkeypatch.delenv("BACKUP_POOLS_EXCLUDE", raising=False)
    rc = pool_paths.main([])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert out == [str(sp / "p" / "fast" / "catA" / "templates")]


def test_main_check_prints_count(tmp_path, monkeypatch, capsys):
    host_root, sp = _make_pool_tree(tmp_path)
    monkeypatch.setattr(pool_paths, "HOST_ROOT", str(host_root))
    monkeypatch.setattr(
        pool_paths,
        "fetch_prefixes",
        lambda *a, **k: [
            "/isard/storage_pools/p/fast/catA/templates",
            "/isard/storage_pools/p/fast/catA/volatile",
        ],
    )
    monkeypatch.delenv("BACKUP_POOLS_EXCLUDE", raising=False)
    rc = pool_paths.main(["--check"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == "1"


def test_main_api_error_is_nonzero_and_never_says_no_pools(monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("apiv4 unreachable")

    monkeypatch.setattr(pool_paths, "fetch_prefixes", boom)
    rc = pool_paths.main([])
    captured = capsys.readouterr()
    assert rc == pool_paths.EXIT_API_ERROR
    assert rc != 0
    assert captured.out.strip() == ""  # never emit an (empty) pool list on error
    assert "apiv4 unreachable" in captured.err
    assert "no pool" not in captured.err.lower()


def test_main_guard_fatal_on_empty_dir(tmp_path, monkeypatch, capsys):
    host_root, sp = _make_pool_tree(tmp_path)
    monkeypatch.setattr(pool_paths, "HOST_ROOT", str(host_root))
    monkeypatch.setattr(
        pool_paths,
        "fetch_prefixes",
        lambda *a, **k: ["/isard/storage_pools/q/slow/catB/templates"],
    )
    rc = pool_paths.main([])
    captured = capsys.readouterr()
    assert rc == pool_paths.EXIT_GUARD_FATAL
    assert captured.out.strip() == ""  # no dirs printed -> job must not archive
    assert "missing" in captured.err.lower() or "empty" in captured.err.lower()


def test_main_check_api_error_is_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(
        pool_paths,
        "fetch_prefixes",
        lambda *a, **k: (_ for _ in ()).throw(OSError("x")),
    )
    rc = pool_paths.main(["--check"])
    assert rc == pool_paths.EXIT_API_ERROR


def test_main_check_counts_unmounted_dirs_too(tmp_path, monkeypatch, capsys):
    """An unmounted pool dir lands in `missing`; --check must still count it, or
    the "not backed up" warning undercounts exactly when a pool went unmounted."""
    host_root, sp = _make_pool_tree(tmp_path)
    monkeypatch.setattr(pool_paths, "HOST_ROOT", str(host_root))
    monkeypatch.setattr(
        pool_paths,
        "fetch_prefixes",
        lambda *a, **k: [
            "/isard/storage_pools/p/fast/catA/templates",  # mounted, has disk
            "/isard/storage_pools/q/slow/catB/templates",  # empty -> missing
        ],
    )
    monkeypatch.delenv("BACKUP_POOLS_EXCLUDE", raising=False)
    rc = pool_paths.main(["--check"])
    out = capsys.readouterr()
    assert rc == 0
    assert out.out.strip() == "2"  # kept(1) + missing(1), not just kept(1)
    assert "unusable" in out.err.lower()
