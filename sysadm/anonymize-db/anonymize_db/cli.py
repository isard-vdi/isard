"""anonymize-db: produce a PII-free rethinkdb-dump tar.gz."""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import shutil
import socket
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from . import dump as dump_mod
from . import fake_storage
from .progress import fmt_dur, human_bytes
from .prune import Pruner
from .safety import (
    assert_devel_usage,
    confirm_destructive_target,
    handle_dependent_services,
    start_containers,
)
from .scrub import Scrubber, get_scrubbers
from .ssh_tunnel import parse_host_port, parse_ssh_target, ssh_tunnel
from .streaming import JsonArrayWriter, iter_json_array

log = logging.getLogger("anonymize-db")


def _stage(num: int, total: int, title: str, elapsed: float | None = None) -> None:
    log.info("")
    log.info("─" * 70)
    suffix = f"   (+{fmt_dur(elapsed)} elapsed)" if elapsed is not None else ""
    log.info("[%d/%d] %s%s", num, total, title, suffix)
    log.info("─" * 70)


def _extract(archive: Path, dest: Path) -> Path:
    """Extract `archive` into `dest`, return the inner `<dump>/<db>` dir."""
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(dest)
    # exactly one top-level dir → inside it, exactly one db dir
    tops = [p for p in dest.iterdir() if p.is_dir()]
    if len(tops) != 1:
        raise RuntimeError(f"unexpected dump layout: {tops}")
    dbs = [p for p in tops[0].iterdir() if p.is_dir()]
    if len(dbs) != 1:
        raise RuntimeError(f"unexpected db layout: {dbs}")
    return dbs[0]


def _repack(src_root: Path, output: Path) -> None:
    """Re-tar the dump root (the `rethinkdb_dump_*` dir) into `output`."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with tarfile.open(output, "w:gz") as tf:
        tf.add(src_root, arcname=src_root.name)


def _scrub_dir_progress(
    db_dir: Path, scrubber: Scrubber, pruner: Pruner | None = None
) -> None:
    """Like _scrub_dir but logs per-table progress."""
    table_scrubbers = get_scrubbers(scrubber)
    json_files = sorted(db_dir.glob("*.json"))
    n = len(json_files)
    sizes = [p.stat().st_size for p in json_files]
    total_bytes = sum(sizes) or 1
    done = 0
    t0 = time.monotonic()
    for i, json_path in enumerate(json_files, 1):
        table = json_path.stem
        size = sizes[i - 1]
        el = time.monotonic() - t0
        # byte-weighted ETA from the work completed so far (big tables dominate)
        eta = f"~{fmt_dur(el / done * (total_bytes - done))} left" if done else ""
        log.info(
            "  scrub [%2d/%2d] %-22s %9s | %3.0f%%  %s elapsed  %s",
            i,
            n,
            table,
            human_bytes(size),
            done / total_bytes * 100,
            fmt_dur(el),
            eta,
        )
        # Stream the table one document at a time so peak RAM stays bounded
        # (~one document + buffer), no matter how large the table is.
        fn = table_scrubbers.get(table)
        prune = pruner is not None and pruner.affects(table)
        tmp = json_path.with_name(json_path.name + ".tmp")
        try:
            with json_path.open() as fin, tmp.open("w") as fout:
                writer = JsonArrayWriter(fout)
                for doc in iter_json_array(fin):
                    # drop old/deleted rows before any work (also saves time)
                    if prune and pruner.should_drop(table, doc):
                        continue
                    doc = scrubber.defensive_sweep(table, doc)
                    # per-table scrubbers take a list; one doc at a time keeps
                    # memory flat. A drop-scrubber returns [] -> nothing written.
                    for out_doc in fn([doc]) if fn is not None else (doc,):
                        writer.write(out_doc)
                writer.close()
            os.replace(tmp, json_path)
        except ValueError:
            log.warning("table %s is not a JSON array; left unchanged", table)
            tmp.unlink(missing_ok=True)
        done += size
    log.info("  scrub pass complete in %s", fmt_dur(time.monotonic() - t0))
    if pruner is not None and pruner.counts:
        log.info(
            "  pruned %d old/deleted rows: %s",
            sum(pruner.counts.values()),
            ", ".join(f"{t} {c}" for t, c in sorted(pruner.counts.items())),
        )
    _cross_table_pass(db_dir, scrubber)


def _cross_table_pass(db_dir: Path, scrubber: Scrubber) -> None:
    """Final consistency pass: rewrite any string leaf in any table whose
    value was registered in scrubber.remap during per-table scrubbing.
    """
    if not scrubber.remap.maps:
        return
    total_keys = sum(len(m) for m in scrubber.remap.maps.values())
    log.info(
        "  cross-table rewrite pass (%d mappings across %d namespaces)",
        total_keys,
        len(scrubber.remap.maps),
    )
    json_files = sorted(db_dir.glob("*.json"))
    grand = 0
    t0 = time.monotonic()
    for json_path in json_files:
        tmp = json_path.with_name(json_path.name + ".tmp")
        n = 0
        try:
            with json_path.open() as fin, tmp.open("w") as fout:
                writer = JsonArrayWriter(fout)
                for doc in iter_json_array(fin):
                    n += scrubber.cross_table_rewrite([doc])
                    writer.write(doc)
                writer.close()
            os.replace(tmp, json_path)
        except ValueError:
            tmp.unlink(missing_ok=True)
            continue
        if n:
            log.info("    %-22s %d replacements", json_path.stem, n)
            grand += n
    log.info(
        "  cross-table rewrite total: %d (%s)", grand, fmt_dur(time.monotonic() - t0)
    )


def _scrub_dir(db_dir: Path, scrubber: Scrubber) -> None:
    table_scrubbers = get_scrubbers(scrubber)
    for json_path in sorted(db_dir.glob("*.json")):
        table = json_path.stem
        with json_path.open() as f:
            rows = json.load(f)
        if not isinstance(rows, list):
            log.warning("skipping non-array %s", json_path)
            continue
        # Defensive sweep first: blanks all unknown sensitive keys.
        # Per-table scrubber runs second so its known-good replacements
        # (bcrypt password hashes, fresh WG keypairs, etc.) are not wiped.
        rows = scrubber.defensive_sweep(table, rows)
        fn = table_scrubbers.get(table)
        if fn is not None:
            rows = fn(rows)
        with json_path.open("w") as f:
            json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    _cross_table_pass(db_dir, scrubber)


def _probe_target(host: str, port: int, db: str) -> tuple[bool, dict[str, int]]:
    """Return (db_exists, {table: row_count}) for the target DB. Empty dict on errors."""
    try:
        from rethinkdb import r
    except Exception as exc:
        log.warning(
            "rethinkdb python driver unavailable (%s); skipping pre-restore probe", exc
        )
        return False, {}
    try:
        conn = r.connect(host=host, port=port, timeout=5)
    except Exception as exc:
        log.warning(
            "could not connect to %s:%d for pre-restore probe (%s)", host, port, exc
        )
        return False, {}
    try:
        dbs = r.db_list().run(conn)
        if db not in dbs:
            return False, {}
        tables = r.db(db).table_list().run(conn)
        counts: dict[str, int] = {}
        for t in tables:
            try:
                n = r.db(db).table(t).count().run(conn)
            except Exception:
                n = -1
            if n:
                counts[t] = n
        return True, counts
    finally:
        with contextlib.suppress(Exception):
            conn.close()


def _ssh_install_name(spec: str) -> tuple[str, set[str]]:
    """Resolve a human target name + accepted aliases from an ssh spec
    ``user@jump[:port]``. For a Warpgate relay the ssh user is
    ``login:install-host``, so the install-host is the meaningful installation
    name the operator must assert."""
    user_host, _ = parse_ssh_target(spec)
    login, sep, jump = user_host.rpartition("@")
    if not sep:
        jump, login = user_host, ""
    name = login.split(":", 1)[1] if ":" in login else jump
    accepted = {name, jump, user_host, spec}
    return name, {a for a in accepted if a}


def _confirm_restore(
    host: str,
    port: int,
    db: str,
    *,
    target_label: str,
    accepted: set[str],
    endpoint: str,
    confirm_target: str | None,
    keep_existing: bool,
) -> None:
    """Probe the target, explain exactly what will be overwritten, and require
    the operator to assert the target installation by name before any write."""
    exists, counts = _probe_target(host, port, db)
    details: list[str] = []
    if exists and counts:
        total = sum(c for c in counts.values() if c > 0)
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:8]
        verb = (
            "FORCE-OVERWRITTEN (matching rows replaced; --keep-existing-db)"
            if keep_existing
            else "DROPPED and fully replaced"
        )
        details.append(
            f"DB '{db}' currently holds {total} rows across {len(counts)} tables"
            f" — it will be {verb}."
        )
        details += [f"  {t:<22} {n} rows" for t, n in top]
        if len(counts) > len(top):
            details.append(f"  ... and {len(counts) - len(top)} more tables")
    elif exists:
        details.append(f"DB '{db}' exists but is empty; it will be (re)created.")
    else:
        # _probe_target collapses 'absent' and 'connect failed' into the same
        # result, so we cannot claim it is empty — name the target regardless.
        details.append(
            f"DB '{db}' is absent or its contents could not be read; "
            "it will be created / overwritten."
        )
    confirm_destructive_target(
        action=f"RESTORE anonymized dump into DB '{db}'",
        target_label=target_label,
        accepted=accepted,
        endpoint=endpoint,
        details=details,
        confirm_target=confirm_target,
        interactive=sys.stdin.isatty(),
    )


def _load_table_json(db_dir: Path, table: str) -> list[dict]:
    path = db_dir / f"{table}.json"
    if not path.exists():
        log.warning("table %s.json missing in dump; treating as empty", table)
        return []
    with path.open() as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        log.warning("table %s.json is not a JSON array; ignoring", table)
        return []
    return rows


def _materialise_fake_storage(args, db_dir: Path | None) -> None:
    container = args.storage_container
    if not fake_storage.container_running(container):
        raise SystemExit(
            f"--with-fake-storage requires the '{container}' container to be running.\n"
            "Start it with: cd /opt/isard/src && docker compose up -d isard-storage"
        )
    will_restore = bool(args.restore_local or args.restore_host or args.restore_ssh)
    # Decide where to read the storage layout from:
    #   1. restore destination (queries DB after restore)
    #   2. dump dir on disk (no restore done; anonymize stage produced it)
    #   3. local isard-db (fake-only mode: no source, no restore)
    if will_restore or db_dir is None:
        if args.restore_host or args.restore_ssh:
            host, port = parse_host_port(args.restore_host or "127.0.0.1", 28015)
        else:
            host, port = "172.31.255.13", 28015
        try:
            from rethinkdb import r
        except Exception as exc:
            raise SystemExit(f"rethinkdb python driver missing: {exc}")
        log.info(
            "connecting to %s:%d/%s for storage layout", host, port, args.restore_db
        )
        conn = r.connect(host=host, port=port, db=args.restore_db, timeout=10)
        try:
            storage_rows = list(r.db(args.restore_db).table("storage").run(conn))
            media_rows = list(r.db(args.restore_db).table("media").run(conn))
        finally:
            with contextlib.suppress(Exception):
                conn.close()
        log.info(
            "loaded %d storage + %d media rows from DB",
            len(storage_rows),
            len(media_rows),
        )
    else:
        # No restore destination: read straight from the anonymized dump.
        storage_rows = _load_table_json(db_dir, "storage")
        media_rows = _load_table_json(db_dir, "media")
        log.info(
            "loaded %d storage + %d media rows from dump",
            len(storage_rows),
            len(media_rows),
        )
    ordered = fake_storage.topo_sort_storages(storage_rows)
    hostname = socket.gethostname()
    confirm_destructive_target(
        action="FAKE STORAGE — create/overwrite qcow2 backing chain + ISO files",
        target_label=hostname,
        accepted={hostname, "localhost", "local", container},
        endpoint=f"container '{container}' /isard on host {hostname}",
        details=[
            f"{len(ordered)} qcow2 files + {len(media_rows)} ISO placeholders will "
            f"be written under /isard inside '{container}'.",
            (
                "Existing files: OVERWRITTEN (rm -f) — --force-replace-files is set."
                if args.force_replace_files
                else "Existing files: kept (skipped)."
            ),
            "If this container's /isard is real or shared storage, REAL disk "
            "images can be destroyed.",
        ],
        confirm_target=args.confirm_target,
        interactive=sys.stdin.isatty(),
    )
    log.info(
        "creating qcow2 chain (%d roots, %d children) inside '%s'",
        sum(1 for r_ in ordered if not (r_.get("parent") or "").strip()),
        sum(1 for r_ in ordered if (r_.get("parent") or "").strip()),
        args.storage_container,
    )
    sc = fake_storage.materialise_storage(
        ordered, args.storage_container, force=args.force_replace_files
    )
    log.info("storage: %s", dict(sc))
    mc = fake_storage.materialise_media(
        media_rows, args.storage_container, force=args.force_replace_files
    )
    log.info("media: %s", dict(mc))
    failures = fake_storage.verify_chains(ordered, args.storage_container)
    if failures:
        log.error("backing chain verification failed:")
        for f in failures:
            log.error("  %s", f)
        raise SystemExit("fake storage verification failed")
    log.info("fake storage chain verified")


def _print_report(scrubber: Scrubber) -> None:
    log.info("scrub report (rows-or-fields touched per table):")
    for t in sorted(scrubber.counts):
        log.info("  %-22s %d", t, scrubber.counts[t])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="anonymize-db",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Produce a PII-free rethinkdb-dump tar.gz of an IsardVDI database, "
            "optionally restore it into a local dev DB, and optionally fake the "
            "qcow2 backing chain + media files so the engine can actually run."
        ),
        epilog=(
            "Common workflows:\n"
            "\n"
            "  Anonymize an existing dump (no DB touched):\n"
            "    anonymize-db --input prod.tar.gz\n"
            "\n"
            "  Pull production via SSH tunnel and just keep the anonymized tar.gz:\n"
            "    anonymize-db --source-ssh user@jump:22\n"
            "\n"
            "  Same, but through a Warpgate bastion (SSH user is 'login:target'):\n"
            "    anonymize-db --source-ssh 'admin:prod-db-node@warpgate.example.com:2222'\n"
            "\n"
            "  Pull production, restore into local isard-db, fake storage, auto-stop\n"
            "  dependent services across the operation:\n"
            "    anonymize-db --source-ssh user@jump:22 \\\n"
            "                 --restore-local --with-fake-storage \\\n"
            "                 --auto-stop-start --yes --confirm-target localhost\n"
            "\n"
            "Safety:\n"
            "  - Anonymized tar.gz is always written (defaults to ./isard-anon-<ts>.tar.gz).\n"
            "  - DUMP / source flags (--input, --source-host, --source-ssh) are READ-ONLY\n"
            "    on the source and can never modify it.\n"
            "  - Every destructive op (restore-*, --with-fake-storage) STOPS, prints what\n"
            "    will be overwritten on which installation, and requires you to assert the\n"
            "    target by name: type it at the prompt, or pass --confirm-target NAME (it\n"
            "    must match the host/install/domain the tool resolves). --yes does NOT\n"
            "    bypass this. For --restore-ssh the name is the Warpgate target, e.g.\n"
            "    'prod-db-node'.\n"
            "  - Invasive ops (restore, fake-storage) require local containers to report\n"
            "    USAGE=devel; otherwise the tool refuses unless --i-know-what-im-doing.\n"
            "  - The target DB is dropped before restore so stale rows don't leak\n"
            "    through (--keep-existing-db opts out). drop_db is hard-restricted to\n"
            "    loopback / 172.31.x targets and never runs against a remote source.\n"
            "  - Default user password after restore: 'pirineus' (admin and everyone).\n"
            "  - guest_properties.credentials are reset to isard / pirineus on every\n"
            "    domain so dev viewers Just Work.\n"
            "\n"
            "See sysadm/anonymize-db/README.md and sysadm/anonymize-db/USAGE.md.\n"
        ),
    )
    g_src = p.add_argument_group(
        "source",
        "Where to get the input dump. Pick exactly one of --input / --source-host / --source-ssh.",
    )
    g_src.add_argument(
        "--input",
        type=Path,
        metavar="FILE",
        help="existing rethinkdb-dump tar.gz to anonymize",
    )
    g_src.add_argument(
        "--source-host",
        metavar="HOST[:PORT]",
        help="dump from this rethinkdb (default port 28015)",
    )
    g_src.add_argument(
        "--source-ssh",
        metavar="USER@JUMP[:PORT]",
        help="open ssh -L tunnel to the SSH jump host, then dump through it. "
        "For Warpgate bastions the SSH user takes the form 'login:target', "
        "e.g. --source-ssh 'admin:prod-db-node@warpgate.example.com:2222'",
    )
    g_src.add_argument(
        "--source-ssh-target",
        metavar="HOST:PORT",
        default="172.31.255.13:28015",
        help="remote DB endpoint reachable from the SSH jump host "
        "(default: 172.31.255.13:28015, the IsardVDI compose bridge). "
        "Ignored with --remote-dump (the dump runs inside the container).",
    )
    g_src.add_argument(
        "--remote-dump",
        action="store_true",
        help="with --source-ssh: run rethinkdb-dump INSIDE the remote container "
        "(export is local to the DB) and stream back only the compressed archive, "
        "instead of tunnelling the DB port. Strongly recommended for large / "
        "production DBs over slow links. Read-only: writes only a temp archive "
        "inside the container, removed afterwards.",
    )
    g_src.add_argument(
        "--remote-dump-container",
        metavar="NAME",
        default="isard-db",
        help="container to run rethinkdb-dump in for --remote-dump (default: isard-db)",
    )
    g_src.add_argument(
        "--remote-dump-dir",
        metavar="DIR",
        default="/data/backups",
        help="directory INSIDE the container for the temp dump (default: "
        "/data/backups — on the big data/storage volume, so it never touches "
        "the host OS disk; only falls back to /tmp, with a warning, if that "
        "lacks free space)",
    )

    g_out = p.add_argument_group("output")
    g_out.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="FILE",
        help="output anonymized tar.gz. Defaults to ./isard-anon-<timestamp>.tar.gz. "
        "A copy is ALWAYS written, even when also restoring.",
    )

    g_trim = p.add_argument_group(
        "trim / shrink (opt-in)",
        "Drop old rows to make the dump smaller and faster. Off by default; "
        "give the flag with no value for the default 30 days, or a day count.",
    )
    g_trim.add_argument(
        "--prune-deleted-days",
        nargs="?",
        const=30,
        default=0,
        type=int,
        metavar="DAYS",
        help="drop entries in a deleted state older than DAYS (default 30): "
        "recycle_bin, storage (deleted/recycled/non_existing), media (deleted).",
    )
    g_trim.add_argument(
        "--cap-history-days",
        nargs="?",
        const=30,
        default=0,
        type=int,
        metavar="DAYS",
        help="keep only the last DAYS (default 30) of the time-series tables: "
        "logs_desktops, logs_users, usage_consumption.",
    )

    g_rst = p.add_argument_group(
        "restore (opt-in)",
        "All restore flags are off by default. Pick one or more.",
    )
    g_rst.add_argument(
        "--restore-local",
        action="store_true",
        help="restore into the local isard-db container (172.31.255.13:28015)",
    )
    g_rst.add_argument(
        "--restore-host",
        metavar="HOST[:PORT]",
        help="restore into this host (drop_db is restricted to "
        "loopback / 172.31.x.x targets)",
    )
    g_rst.add_argument(
        "--restore-ssh",
        metavar="USER@JUMP[:PORT]",
        help="open ssh -L tunnel and restore through it",
    )
    g_rst.add_argument(
        "--restore-ssh-target",
        metavar="HOST:PORT",
        default="172.31.255.13:28015",
        help="remote DB endpoint reachable from the SSH jump host (default: 172.31.255.13:28015)",
    )
    g_rst.add_argument(
        "--restore-db",
        default="isard",
        metavar="NAME",
        help="target DB name (default: isard)",
    )
    g_rst.add_argument(
        "--keep-existing-db",
        action="store_true",
        help="do NOT drop the target DB before restore. Default drops the "
        "DB first so stale rows from previous restores don't survive.",
    )

    g_stor = p.add_argument_group("fake storage (opt-in)")
    g_stor.add_argument(
        "--with-fake-storage",
        action="store_true",
        help="create fake qcow2 backing chain + zero-byte ISO files inside the storage "
        "container so the engine can start desktops, derive templates, etc. Layout is "
        "read from the restored DB (with a restore flag), the anonymized dump (with a "
        "source but no restore), or the local isard-db (when given alone, with no "
        "source). Use --restore-host to target a different DB endpoint in the last case.",
    )
    g_stor.add_argument(
        "--storage-container",
        default="isard-storage",
        metavar="NAME",
        help="container running qemu-img with /isard mounted (default: isard-storage). "
        "Bring it up with: cd /opt/isard/src && docker compose up -d isard-storage",
    )
    g_stor.add_argument(
        "--force-replace-files",
        action="store_true",
        help="overwrite existing qcow2 / ISO files (default: skip if present)",
    )

    g_safe = p.add_argument_group("safety")
    g_safe.add_argument(
        "--auto-stop-start",
        action="store_true",
        help="stop dependent isard-* services (api, engine, ...) before the invasive "
        "ops and start them again after, even on failure.",
    )
    g_safe.add_argument(
        "--i-know-what-im-doing",
        action="store_true",
        help="bypass the USAGE=devel gate ONLY when no container reports USAGE. "
        "Never bypasses USAGE=production/staging.",
    )
    g_safe.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="auto-confirm the dependent-services prompt. Does NOT bypass the "
        "destructive-target confirmation (use --confirm-target for that).",
    )
    g_safe.add_argument(
        "--confirm-target",
        metavar="NAME",
        default=None,
        help="non-interactive confirmation for destructive ops (restore / "
        "fake-storage). Must exactly match the target installation name/host/"
        "domain the tool resolves, otherwise the run aborts before writing "
        "anything. Required when there is no TTY.",
    )

    g_misc = p.add_argument_group("misc")
    g_misc.add_argument(
        "--seed",
        type=int,
        default=0,
        metavar="N",
        help="Faker seed for deterministic output (default: 0)",
    )
    g_misc.add_argument(
        "-v", "--verbose", action="store_true", help="enable DEBUG logging"
    )
    args = p.parse_args(argv)
    fake_only = bool(
        args.with_fake_storage
        and not (args.input or args.source_host or args.source_ssh)
    )
    if not (
        args.input or args.source_host or args.source_ssh or args.with_fake_storage
    ):
        p.error(
            "one of --input, --source-host, --source-ssh is required "
            "(or --with-fake-storage alone for storage-only mode)"
        )
    if args.input and (args.source_host or args.source_ssh):
        p.error("--input is mutually exclusive with --source-host/--source-ssh")
    if args.remote_dump and not args.source_ssh:
        p.error("--remote-dump requires --source-ssh")
    if args.output is None and not fake_only:
        from datetime import datetime

        args.output = Path.cwd() / f"isard-anon-{datetime.now():%Y%m%dT%H%M%S}.tar.gz"

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    workdir = Path(tempfile.mkdtemp(prefix="anonymize-db-"))
    log.info("workdir: %s", workdir)
    if not fake_only:
        log.info("output:  %s", args.output)
    will_restore = bool(args.restore_local or args.restore_host or args.restore_ssh)
    stage_names: list[str] = []
    if not fake_only:
        stage_names += ["dump", "anonymize"]
    if will_restore:
        stage_names.append("restore")
    if args.with_fake_storage:
        stage_names.append("fake-storage")
    total_stages = len(stage_names)
    log.info("plan: %s", " → ".join(stage_names))
    stage_no = 0
    run_t0 = time.monotonic()
    db_dir: Path | None = None
    try:
        if not fake_only:
            # --- acquire dump ---
            stage_no += 1
            _stage(stage_no, total_stages, "DUMP source DB", time.monotonic() - run_t0)
            dump_tgz = workdir / "input.tar.gz"
            if args.input:
                log.info("copying provided input %s", args.input)
                shutil.copy(args.input, dump_tgz)
            elif args.source_ssh and args.remote_dump:
                # Run rethinkdb-dump inside the remote container (local to the
                # DB) and stream back only the compressed archive — read-only,
                # no DB port tunnel. Best for large/production DBs over slow links.
                user_host, ssh_port = parse_ssh_target(args.source_ssh)
                dump_mod.rethinkdb_dump_remote_docker(
                    user_host,
                    ssh_port,
                    dump_tgz,
                    container=args.remote_dump_container,
                    remote_dir=args.remote_dump_dir,
                )
            else:
                host, port = parse_host_port(args.source_host or "127.0.0.1", 28015)
                with contextlib.ExitStack() as stack:
                    if args.source_ssh:
                        user_host, ssh_port = parse_ssh_target(args.source_ssh)
                        rh, rp = parse_host_port(args.source_ssh_target, 28015)
                        local = stack.enter_context(
                            ssh_tunnel(user_host, ssh_port, rh, rp)
                        )
                        host, port = "127.0.0.1", local
                    dump_mod.rethinkdb_dump(host, port, dump_tgz)

            # --- extract, scrub, repack ---
            stage_no += 1
            _stage(stage_no, total_stages, "ANONYMIZE", time.monotonic() - run_t0)
            extract_dir = workdir / "extracted"
            extract_dir.mkdir()
            db_dir = _extract(dump_tgz, extract_dir)
            json_files = sorted(db_dir.glob("*.json"))
            log.info("extracted %d tables to %s", len(json_files), db_dir)
            scrubber = Scrubber(seed=args.seed)
            pruner = Pruner(
                prune_deleted_days=args.prune_deleted_days,
                cap_history_days=args.cap_history_days,
            )
            if pruner.active:
                log.info(
                    "trim: prune-deleted=%s cap-history=%s",
                    f"{args.prune_deleted_days}d" if args.prune_deleted_days else "off",
                    f"{args.cap_history_days}d" if args.cap_history_days else "off",
                )
            _scrub_dir_progress(db_dir, scrubber, pruner)
            log.info("repacking → %s", args.output)
            _repack(db_dir.parent, args.output)
            _print_report(scrubber)
            log.info(
                "anonymized tar.gz: %s (%s)",
                args.output,
                human_bytes(args.output.stat().st_size),
            )

        # --- optional restore (off by default; must be explicitly opted in) ---
        invasive = bool(
            args.restore_local
            or args.restore_host
            or args.restore_ssh
            or args.with_fake_storage
        )
        stopped_services: list[str] = []
        if invasive:
            # Refuse if any local isard-* container is NOT USAGE=devel.
            assert_devel_usage(
                allow_override=getattr(args, "i_know_what_im_doing", False)
            )
            # Stop dependent services (or warn) so they don't see the DB swap.
            stopped_services = handle_dependent_services(
                assume_yes=args.yes,
                auto_stop_start=args.auto_stop_start,
            )
        # Track the resolved source host so drop_db can refuse to clobber it.
        # When SSH tunneling, the source machine is the SSH jump host, NOT the
        # in-network IP of the remote DB (which may collide with a local docker
        # bridge address e.g. 172.31.255.13 — same string, different machine).
        if args.source_ssh:
            source_endpoint = (
                f"ssh:{args.source_ssh}"  # remote, never matches a local restore host
            )
        elif args.source_host:
            source_endpoint, _ = parse_host_port(args.source_host, 28015)
        else:
            source_endpoint = None

        try:
            if will_restore:
                stage_no += 1
                _stage(
                    stage_no,
                    total_stages,
                    "RESTORE into target DB",
                    time.monotonic() - run_t0,
                )
            if args.restore_local:
                # Probe via the container's bridge IP for the warning, then run
                # rethinkdb-restore *inside* the isard-db container itself.
                host, port = "172.31.255.13", 28015
                log.info(
                    "target: isard-db (%s:%d / db=%s)", host, port, args.restore_db
                )
                _confirm_restore(
                    host,
                    port,
                    args.restore_db,
                    target_label="localhost",
                    accepted={
                        "localhost",
                        "local",
                        "127.0.0.1",
                        "172.31.255.13",
                        "isard-db",
                    },
                    endpoint="local isard-db (172.31.255.13:28015, docker exec)",
                    confirm_target=args.confirm_target,
                    keep_existing=args.keep_existing_db,
                )
                if not args.keep_existing_db:
                    dump_mod.drop_db(
                        host, port, args.restore_db, source_host=source_endpoint
                    )
                dump_mod.rethinkdb_restore_via_isard_db(args.output)
            elif args.restore_host or args.restore_ssh:
                host, port = parse_host_port(args.restore_host or "127.0.0.1", 28015)
                if args.restore_ssh:
                    target_label, accepted = _ssh_install_name(args.restore_ssh)
                    endpoint = (
                        f"{args.restore_ssh} -> {args.restore_ssh_target} "
                        f"(db={args.restore_db})"
                    )
                else:
                    rhost, _ = parse_host_port(args.restore_host, 28015)
                    target_label = rhost
                    accepted = {rhost, args.restore_host}
                    endpoint = f"{args.restore_host} (db={args.restore_db})"
                with contextlib.ExitStack() as stack:
                    if args.restore_ssh:
                        user_host, ssh_port = parse_ssh_target(args.restore_ssh)
                        rh, rp = parse_host_port(args.restore_ssh_target, 28015)
                        local = stack.enter_context(
                            ssh_tunnel(user_host, ssh_port, rh, rp)
                        )
                        host, port = "127.0.0.1", local
                    _confirm_restore(
                        host,
                        port,
                        args.restore_db,
                        target_label=target_label,
                        accepted=accepted,
                        endpoint=endpoint,
                        confirm_target=args.confirm_target,
                        keep_existing=args.keep_existing_db,
                    )
                    if not args.keep_existing_db:
                        dump_mod.drop_db(
                            host, port, args.restore_db, source_host=source_endpoint
                        )
                    dump_mod.rethinkdb_restore(host, port, args.output)

            # --- optional fake storage materialisation ---
            if args.with_fake_storage:
                stage_no += 1
                _stage(
                    stage_no,
                    total_stages,
                    "FAKE STORAGE (qcow2 chain + ISOs)",
                    time.monotonic() - run_t0,
                )
                _materialise_fake_storage(args, db_dir)
        finally:
            # Always restart whatever we stopped, even if the restore blew up.
            if stopped_services:
                start_containers(stopped_services)

        log.info("✓ all stages complete in %s", fmt_dur(time.monotonic() - run_t0))
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
