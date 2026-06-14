"""Safety gates for invasive actions.

Two gates:

1. `assert_devel_usage` — refuses unless local containers are USAGE=devel.
2. `warn_dependent_services` — warns if any isard-* services that connect to
    isard-db are running while we are about to overwrite it; they will see
    a DB swap underneath them and should be stopped first.



`isard-db` itself does not carry USAGE; the marker lives on the Python service
containers (apiv4, engine, webapp, notifier, scheduler). We inspect every
running container whose name starts with `isard-` and:

  - if any of them advertises USAGE != devel  -> abort (this looks like prod / staging)
  - if none of them advertises USAGE at all   -> abort (ambiguous; force opt-in)
  - if at least one advertises USAGE=devel    -> proceed
"""

from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)


def confirm_destructive_target(
    *,
    action: str,
    target_label: str,
    accepted: set[str],
    endpoint: str,
    details: list[str],
    confirm_target: str | None,
    interactive: bool = True,
) -> None:
    """Hard STOP before overwriting an installation.

    Prints exactly WHAT will be overwritten on WHICH installation, then refuses
    to continue until the operator asserts the target by typing its name/domain.
    This is deliberately NOT bypassable by ``--yes`` (which only auto-answers the
    softer prompts): a destructive write to *any* installation always requires
    the operator to name that installation.

    - non-interactive (CI / no TTY): pass ``--confirm-target`` and it must match
      one of ``accepted`` (case-insensitive).
    - interactive: the operator must type a value matching ``accepted``.

    Raises ``SystemExit`` on mismatch / missing confirmation.
    """
    norm = {a.strip().lower() for a in accepted if a}
    bar = "!" * 72
    log.warning(bar)
    log.warning("STOP — DESTRUCTIVE ACTION: %s", action)
    log.warning("Target installation : %s", target_label)
    log.warning("Endpoint            : %s", endpoint)
    log.warning("The following WILL BE OVERWRITTEN on that installation:")
    for d in details:
        log.warning("    %s", d)
    log.warning("This is NOT reversible.")
    log.warning(bar)

    if confirm_target is not None:
        if confirm_target.strip().lower() in norm:
            log.warning("--confirm-target matches '%s'; proceeding.", target_label)
            return
        raise SystemExit(
            f"REFUSING: --confirm-target '{confirm_target}' does not match the "
            f"target installation '{target_label}'. Nothing was written."
        )

    if not interactive:
        raise SystemExit(
            "REFUSING to run a destructive action without confirmation (no TTY).\n"
            f"Re-run with --confirm-target '{target_label}' to assert the target."
        )

    ans = (
        input(
            f"\nType the target installation name/domain to confirm the overwrite "
            f"of '{target_label}': "
        )
        .strip()
        .lower()
    )
    if ans not in norm:
        raise SystemExit(
            f"REFUSING: '{ans}' does not match the target installation "
            f"'{target_label}'. Nothing was written."
        )
    log.warning("confirmed target '%s'; proceeding.", target_label)


def _running_isard_containers() -> list[str]:
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--format", "{{.Names}}"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception as exc:
        log.warning("could not list docker containers: %s", exc)
        return []
    return [n for n in out.splitlines() if n.startswith("isard-")]


def _container_usage(name: str) -> str | None:
    """Return the value of USAGE in `name`'s env, or None if not set."""
    try:
        env_lines = subprocess.check_output(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .Config.Env}}{{println .}}{{end}}",
                name,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return None
    for line in env_lines.splitlines():
        if line.startswith("USAGE="):
            return line.split("=", 1)[1].strip()
    return None


def assert_devel_usage(allow_override: bool = False) -> None:
    """Raise SystemExit unless local containers are clearly USAGE=devel.

    `allow_override` (--i-know-what-im-doing) bypasses *only* the
    "no USAGE marker found anywhere" branch. A container that reports
    USAGE != devel is *never* overridable by this flag.
    """
    names = _running_isard_containers()
    if not names:
        if allow_override:
            log.warning(
                "no running isard-* containers; proceeding under --i-know-what-im-doing"
            )
            return
        raise SystemExit(
            "refusing to act: no running isard-* containers found.\n"
            "Bring the dev stack up first (docker compose up -d), or pass "
            "--i-know-what-im-doing to bypass."
        )
    devel: list[str] = []
    other: list[tuple[str, str]] = []
    unmarked: list[str] = []
    for n in names:
        u = _container_usage(n)
        if u is None or u == "":
            # Compose may pass `USAGE=` (empty) to every service when the
            # var is undefined in isardvdi.cfg; treat that as "unmarked"
            # rather than "different value".
            unmarked.append(n)
        elif u == "devel":
            devel.append(n)
        else:
            other.append((n, u))
    if other:
        msg_lines = [
            "REFUSING to overwrite/anonymize: at least one local container is NOT USAGE=devel:",
            *(f"  - {n}: USAGE={u}" for n, u in other),
            "This looks like a production or staging environment. Aborting.",
        ]
        raise SystemExit("\n".join(msg_lines))
    if not devel:
        if allow_override:
            log.warning(
                "no container advertises USAGE=devel; proceeding under "
                "--i-know-what-im-doing (containers checked: %s)",
                ", ".join(names),
            )
            return
        raise SystemExit(
            "refusing to act: no running container reports USAGE=devel "
            f"(checked: {', '.join(names)}).\n"
            "Pass --i-know-what-im-doing to bypass after confirming this is a dev box."
        )
    log.info("safety gate ok: USAGE=devel on %s", ", ".join(devel))
    if unmarked:
        log.debug("containers without USAGE marker (ignored): %s", ", ".join(unmarked))


# Containers that are *not* dependent — the DB itself, the storage helper, and
# pure infra without a DB connection. Anything else that's running while we
# overwrite isard-db will see a DB swap and is likely to misbehave.
_NON_DEPENDENT = {"isard-db", "isard-storage", "isard-redis", "isard-squid"}


def running_dependent_services() -> list[str]:
    return [n for n in _running_isard_containers() if n not in _NON_DEPENDENT]


def stop_containers(names: list[str]) -> list[str]:
    if not names:
        return []
    log.info("stopping containers: %s", ", ".join(names))
    subprocess.run(["docker", "stop", *names], check=False, capture_output=True)
    # Re-check what's actually stopped now (some may have already been stopped).
    still_running = set(_running_isard_containers())
    return [n for n in names if n not in still_running]


def start_containers(names: list[str]) -> None:
    if not names:
        return
    log.info("starting containers: %s", ", ".join(names))
    subprocess.run(["docker", "start", *names], check=False, capture_output=True)


def handle_dependent_services(
    assume_yes: bool, auto_stop_start: bool, interactive: bool = True
) -> list[str]:
    """If isard-* services connect to isard-db are running, decide what to do.

    Returns the list of containers that were stopped *by us* and should be
    restarted by the caller after the invasive op completes.
    """
    deps = running_dependent_services()
    if not deps:
        return []
    deps = sorted(deps)
    log.warning("=" * 70)
    log.warning("These running services connect to isard-db and will see a DB")
    log.warning("swap underneath them while restore runs:")
    for n in deps:
        log.warning("    %s", n)
    log.warning("=" * 70)
    if auto_stop_start:
        log.warning("--auto-stop-start: stopping them now, will restart after restore.")
        stopped = stop_containers(deps)
        return stopped
    log.warning("Tip: re-run with --auto-stop-start to handle this automatically, or")
    log.warning("manually run, in another shell, /opt/isard/src:")
    log.warning("    docker compose stop %s", " ".join(deps))
    log.warning("    # ... let anonymize-db finish ...")
    log.warning("    docker compose start %s", " ".join(deps))
    if assume_yes:
        log.warning("--yes given; proceeding with services still running.")
        return []
    if not interactive:
        raise SystemExit("refusing to proceed with dependent services running (no TTY)")
    ans = (
        input("Type 'yes' to proceed anyway, anything else to abort: ").strip().lower()
    )
    if ans != "yes":
        raise SystemExit(
            "aborted: stop the listed services first, or re-run with --auto-stop-start."
        )
    return []
