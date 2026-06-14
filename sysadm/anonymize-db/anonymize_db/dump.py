"""Wrappers for `rethinkdb-dump` / `rethinkdb-restore`.

Strategy:
- If `rethinkdb-dump` is on PATH, use it directly.
- Else run it inside a docker container using the running `isard-db` image.
"""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

from .progress import fmt_dur, human_bytes, report_file_growth

log = logging.getLogger(__name__)

DEFAULT_IMAGE = "registry.gitlab.com/isard/isardvdi/db:main"


def _ssh_base(ssh_port: int) -> list[str]:
    return [
        "ssh",
        "-T",  # no PTY: keep the streamed archive binary-clean
        "-o",
        "BatchMode=yes",
        "-o",
        "ServerAliveInterval=30",
        "-p",
        str(ssh_port),
    ]


def _remote_container_free_kb(
    ssh_user_host: str, ssh_port: int, container: str, directory: str, sudo: bool
) -> int:
    """Free KiB on `directory` *inside* `container`, or -1 if it can't be read."""
    s = "sudo " if sudo else ""
    inner = f"mkdir -p {shlex.quote(directory)} 2>/dev/null; df -Pk {shlex.quote(directory)} | tail -1"
    cmd = _ssh_base(ssh_port) + [
        ssh_user_host,
        f"{s}docker exec {shlex.quote(container)} sh -c {shlex.quote(inner)}",
    ]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return -1
    parts = out.split()
    # df -P columns: Filesystem 1K-blocks Used Available Capacity Mounted-on
    try:
        return int(parts[3])
    except (IndexError, ValueError):
        return -1


def rethinkdb_dump_remote_docker(
    ssh_user_host: str,
    ssh_port: int,
    output: Path,
    *,
    container: str = "isard-db",
    remote_dir: str = "/data/backups",
    fallback_dir: str = "/tmp",
    sudo: bool = True,
    min_free_kb: int = 8 * 1024 * 1024,
) -> None:
    """Dump the source DB by running `rethinkdb-dump` INSIDE the remote container
    (so the export is local to the DB and fast), then stream the resulting
    compressed archive back over SSH to `output`.

    Read-only with respect to the installation: the only thing written on the
    remote is a single temporary `.tar.gz` inside the container — in `remote_dir`
    (default `/data/backups`, on the big data/storage volume so the host OS disk
    is never touched) — and it is removed afterwards (shell `trap ... EXIT`). It
    only falls back to `fallback_dir` (`/tmp`, host overlay) with a warning when
    the data volume lacks space. DB data, the DRBD/data volume contents,
    containers, config and services are never modified.

    Suited to large / production DBs over slow links: only the gzipped archive
    crosses the network, not the full uncompressed JSON. Requires non-interactive
    `sudo docker exec` on the jump host.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    s = "sudo " if sudo else ""
    qc = shlex.quote(container)

    chosen: str | None = None
    for d in (remote_dir, fallback_dir):
        free = _remote_container_free_kb(ssh_user_host, ssh_port, container, d, sudo)
        log.info(
            "container %s dir %s free: %s",
            container,
            d,
            f"{free // 1024} MB" if free >= 0 else "unknown",
        )
        if free >= min_free_kb:
            chosen = d
            if d == fallback_dir and fallback_dir == "/tmp":
                log.warning(
                    "falling back to %s (container overlay = HOST OS disk); the "
                    "data volume %s lacked space. Watch host disk usage.",
                    fallback_dir,
                    remote_dir,
                )
            break
    if chosen is None:
        raise SystemExit(
            f"remote dump: neither {remote_dir} nor {fallback_dir} has "
            f">= {min_free_kb // 1024 // 1024} GB free inside '{container}'."
        )

    # One atomic remote command: dump -> stream archive to stdout -> always
    # remove the temp file (even on failure/interrupt). rethinkdb-dump's own
    # progress goes to stderr (1>&2) so it cannot corrupt the binary stdout.
    # `-e TMPDIR=<chosen>` makes rethinkdb-dump's mkdtemp() working dir land in
    # the same chosen dir as the archive (it otherwise defaults to the
    # container's /tmp), so the free-space check actually covers it.
    qd = shlex.quote(chosen)
    inner = (
        f"F={qd}/anonsrc-$$.tar.gz; "
        f"trap '{s}docker exec {qc} rm -f \"$F\" >/dev/null 2>&1 || true' EXIT; "
        f'{s}docker exec -e TMPDIR={qd} {qc} rethinkdb-dump -f "$F" 1>&2; '
        f'{s}docker exec {qc} cat "$F"'
    )
    cmd = _ssh_base(ssh_port) + [ssh_user_host, inner]
    log.info(
        "remote dump: %sdocker exec %s rethinkdb-dump in %s on %s (streaming back)",
        s,
        container,
        chosen,
        ssh_user_host,
    )
    t0 = time.monotonic()
    with output.open("wb") as fout:
        with report_file_growth(
            output,
            log,
            label="received",
            idle_msg=f"running rethinkdb-dump inside {container} (no transfer yet)…",
        ):
            proc = subprocess.run(cmd, stdout=fout, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise SystemExit(
            "remote dump failed (rc=%d): %s"
            % (proc.returncode, proc.stderr.decode("utf-8", "replace").strip()[-800:])
        )
    size = output.stat().st_size
    if size == 0:
        raise SystemExit("remote dump produced an empty archive (transfer failed?)")
    try:
        with tarfile.open(output, "r:gz") as t:
            _ = t.next()
    except Exception as exc:
        raise SystemExit(
            f"remote dump archive is not a valid gzip tar (transfer corruption?): {exc}"
        )
    elapsed = time.monotonic() - t0
    log.info(
        "remote dump archive received: %s (%s in %s, avg %.1f MB/s), integrity OK",
        output,
        human_bytes(size),
        fmt_dur(elapsed),
        size / 1e6 / elapsed if elapsed > 0 else 0.0,
    )


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _docker_image() -> str:
    """Discover the image of the running `isard-db` container, fall back to default."""
    try:
        out = subprocess.check_output(
            ["docker", "inspect", "-f", "{{.Config.Image}}", "isard-db"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return out
    except Exception:
        pass
    return DEFAULT_IMAGE


def rethinkdb_dump(host: str, port: int, output: Path) -> None:
    """Dump remote DB to `output` (a *.tar.gz file)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if _have("rethinkdb-dump"):
        cmd = ["rethinkdb-dump", "-c", f"{host}:{port}", "-f", str(output)]
        log.info("dump: %s", " ".join(cmd))
        subprocess.run(cmd, check=True)
        return
    image = _docker_image()
    out_dir = output.parent.resolve()
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "-v",
        f"{out_dir}:/dump",
        "--entrypoint",
        "/usr/local/bin/rethinkdb-dump",
        image,
        "-c",
        f"{host}:{port}",
        "-f",
        f"/dump/{output.name}",
    ]
    log.info("dump (docker): %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _is_safe_local_target(host: str) -> bool:
    """True iff `host` is loopback or the IsardVDI compose bridge.

    drop_db must never run against a remote / production host, so we whitelist
    only addresses that can plausibly be a local dev DB:
      - any 127.0.0.0/8 address
      - 172.31.x.x  (IsardVDI default docker bridge)
      - localhost
    """
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    if host.startswith("127."):
        return True
    if host.startswith("172.31."):
        return True
    return False


def drop_db(host: str, port: int, db: str, source_host: str | None = None) -> None:
    """Drop `db` if present so leftover rows don't survive `rethinkdb-restore`.

    `rethinkdb-restore --force` allows writes into existing tables but does NOT
    truncate them, so rows present in the target DB but absent in the dump
    survive. Dropping the DB first guarantees the restored DB is exactly the
    contents of the dump.

    Hard safety:
      - refuses if `host` is not a recognised local dev address
      - refuses if `host` equals the source we just dumped from
    Either case raises SystemExit. Callers can opt out with --keep-existing-db.
    """
    if source_host and host == source_host:
        raise SystemExit(
            f"REFUSING to drop_db: restore host ({host}) equals the source we "
            "just dumped from. This would destroy the source DB."
        )
    if not _is_safe_local_target(host):
        raise SystemExit(
            f"REFUSING to drop_db on '{host}:{port}': not a recognised local "
            "dev endpoint (allowed: 127.x, localhost, 172.31.x). "
            "Re-run with --keep-existing-db to skip the drop step."
        )
    from rethinkdb import r

    log.info("dropping db '%s' on %s:%d (clean restore)", db, host, port)
    conn = r.connect(host=host, port=port, timeout=10)
    try:
        if db in r.db_list().run(conn):
            r.db_drop(db).run(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def rethinkdb_restore_via_isard_db(archive: Path, force: bool = True) -> None:
    """Restore by copying the archive into the running isard-db container and
    running rethinkdb-restore there against localhost. Avoids any networking
    concern when targeting the local stack."""
    log.info("restore (docker exec isard-db): %s", archive)
    subprocess.run(
        ["docker", "cp", str(archive), f"isard-db:/tmp/{archive.name}"], check=True
    )
    cmd = [
        "docker",
        "exec",
        "isard-db",
        "/usr/local/bin/rethinkdb-restore",
        "-c",
        "127.0.0.1:28015",
    ]
    if force:
        cmd.append("--force")
    cmd.append(f"/tmp/{archive.name}")
    subprocess.run(cmd, check=True)
    subprocess.run(
        ["docker", "exec", "isard-db", "rm", "-f", f"/tmp/{archive.name}"], check=False
    )


def rethinkdb_restore(host: str, port: int, archive: Path, force: bool = True) -> None:
    """Restore `archive` (*.tar.gz) into the DB at host:port."""
    if _have("rethinkdb-restore"):
        cmd = ["rethinkdb-restore", "-c", f"{host}:{port}"]
        if force:
            cmd.append("--force")
        cmd.append(str(archive))
        log.info("restore: %s", " ".join(cmd))
        subprocess.run(cmd, check=True)
        return
    image = _docker_image()
    arch_dir = archive.parent.resolve()
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "-v",
        f"{arch_dir}:/dump",
        "--entrypoint",
        "/usr/local/bin/rethinkdb-restore",
        image,
        "-c",
        f"{host}:{port}",
    ]
    if force:
        cmd.append("--force")
    cmd.append(f"/dump/{archive.name}")
    log.info("restore (docker): %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
