"""Hypervisor graceful shutdown orchestrator.

Invoked from start.sh's SIGTERM/SIGINT/SIGQUIT trap. Runs the full shutdown
sequence:

    T=0    in parallel: API unregister + ACPI soft-shutdown to every guest
    T=15   hard-destroy any guest that didn't power off
    T=15+  wipe every sysfs mdev on every GPU
    exit

Every step is wrapped so a failure in one does not abort the rest — the
hypervisor must do as much as it can before terminating.
"""

import logging
import os
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import jwt
import requests

log = logging.getLogger("hypervisor.shutdown")
if not log.handlers:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(asctime)s shutdown: %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

GUEST_SHUTDOWN_TIMEOUT = int(os.environ.get("GUEST_SHUTDOWN_TIMEOUT", "15"))
API_DELETE_TIMEOUT = float(os.environ.get("HYPER_API_DELETE_TIMEOUT", "4"))
DESTROY_MAX_WORKERS = 16


def _api_base_url():
    api_domain = os.environ.get("API_DOMAIN", False)
    if api_domain and api_domain != "isard-api":
        return "https://" + api_domain + "/api/v3/"
    return "http://isard-api:5000/api/v3/"


def _api_auth_header():
    token = jwt.encode(
        {
            "exp": datetime.utcnow() + timedelta(seconds=90),
            "kid": "isardvdi-hypervisors",
            "session_id": "isardvdi-service",
            "data": {"role_id": "hypervisor", "category_id": "default"},
        },
        os.environ["API_HYPERVISORS_SECRET"],
        algorithm="HS256",
    )
    return {"Authorization": "Bearer " + token}


def api_unregister():
    """Fire DELETE /hypervisor/<id> with a short timeout. Best effort.

    The API handler writes the important DB flags (enabled=False,
    status=Deleting, forced_hyp=True, all-domain stop) in the first few
    hundred milliseconds and then polls up to ~10s waiting for the engine
    orchestrator to reap the row. We do NOT need to wait for that poll —
    the engine picks up from the DB on its own.
    """
    hyper_id = os.environ.get("HYPER_ID", "isard-hypervisor")
    url = _api_base_url() + "hypervisor/" + hyper_id
    try:
        resp = requests.delete(
            url,
            headers=_api_auth_header(),
            verify=False,
            timeout=API_DELETE_TIMEOUT,
        )
        log.info("api DELETE %s -> %s", hyper_id, resp.status_code)
    except requests.exceptions.Timeout:
        log.warning(
            "api DELETE %s timed out after %.1fs (early DB writes "
            "should already have landed)",
            hyper_id,
            API_DELETE_TIMEOUT,
        )
    except Exception as e:
        log.warning("api DELETE %s failed: %s", hyper_id, e)


def _libvirt_connect():
    """Open libvirt. Imported lazily so this module is usable without
    libvirt installed (tests, linting). Returns None on failure."""
    try:
        import libvirt  # noqa: WPS433
    except ImportError as e:
        log.error("libvirt python binding missing: %s", e)
        return None, None
    try:
        conn = libvirt.open("qemu:///system")
        if conn is None:
            log.error("libvirt.open returned None")
            return None, None
        return conn, libvirt
    except Exception as e:
        log.error("libvirt.open failed: %s", e)
        return None, None


def _active_domains(conn, libvirt_mod):
    try:
        return conn.listAllDomains(libvirt_mod.VIR_CONNECT_LIST_DOMAINS_ACTIVE)
    except Exception as e:
        log.warning("listAllDomains failed: %s", e)
        return []


def acpi_shutdown_all():
    """Send ACPI power-button signal to every running domain.

    Returns the count of signals issued. libvirt's shutdownFlags is
    non-blocking: it enqueues the ACPI request and returns, so firing
    all signals in a tight loop takes <1s even for dozens of guests.
    """
    conn, libvirt_mod = _libvirt_connect()
    if not conn:
        return 0
    try:
        domains = _active_domains(conn, libvirt_mod)
        count = 0
        for d in domains:
            try:
                d.shutdownFlags(libvirt_mod.VIR_DOMAIN_SHUTDOWN_ACPI_POWER_BTN)
                count += 1
            except Exception as e:
                log.warning("ACPI shutdown %s failed: %s", d.name(), e)
        log.info("ACPI to %d domain(s)", count)
        return count
    finally:
        try:
            conn.close()
        except Exception:
            pass


def wait_for_shutdown(deadline_seconds):
    """Poll until every active domain has exited or deadline passes.

    Returns (remaining_count, elapsed_seconds).
    """
    conn, libvirt_mod = _libvirt_connect()
    if not conn:
        return 0, 0.0
    t0 = time.monotonic()
    deadline = t0 + deadline_seconds
    try:
        while True:
            domains = _active_domains(conn, libvirt_mod)
            if not domains:
                elapsed = time.monotonic() - t0
                log.info("drained all domains in %.1fs", elapsed)
                return 0, elapsed
            if time.monotonic() >= deadline:
                elapsed = time.monotonic() - t0
                log.info(
                    "drain deadline reached at %.1fs with %d domain(s) still running",
                    elapsed,
                    len(domains),
                )
                return len(domains), elapsed
            time.sleep(0.5)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def destroy_remaining_parallel():
    """Hard-destroy every domain still active. Parallel per domain."""
    conn, libvirt_mod = _libvirt_connect()
    if not conn:
        return 0
    try:
        domains = _active_domains(conn, libvirt_mod)
        if not domains:
            return 0

        def _destroy(d):
            name = d.name()
            try:
                d.destroy()
                return name, None
            except Exception as e:
                return name, e

        with ThreadPoolExecutor(
            max_workers=min(DESTROY_MAX_WORKERS, max(1, len(domains)))
        ) as pool:
            results = list(pool.map(_destroy, domains))
        destroyed = 0
        for name, err in results:
            if err is None:
                destroyed += 1
            else:
                log.warning("destroy %s failed: %s", name, err)
        log.info("destroyed %d leftover domain(s)", destroyed)
        return destroyed
    finally:
        try:
            conn.close()
        except Exception:
            pass


def reset_mdevs_on_all_gpus():
    """Wipe every sysfs mdev on every nvidia-bound PF."""
    try:
        # Imported lazily so a missing libvirt/nvidia-smi during dev
        # doesn't prevent this module from loading.
        sys.path.insert(0, "/src/lib")
        from gpu_discovery import reset_all_mdevs  # noqa: WPS433

        n = reset_all_mdevs()
        log.info("mdevs reset on %d GPU(s)", n)
    except Exception as e:
        log.warning("mdev reset failed: %s", e)


def run_shutdown():
    """Orchestrate the full shutdown sequence. Always returns without raising."""
    log.info(
        "begin (guest timeout=%ds, api timeout=%.1fs)",
        GUEST_SHUTDOWN_TIMEOUT,
        API_DELETE_TIMEOUT,
    )
    t_start = time.monotonic()

    api_thread = threading.Thread(target=api_unregister, name="api-unregister")
    acpi_thread = threading.Thread(target=acpi_shutdown_all, name="acpi-shutdown")
    api_thread.start()
    acpi_thread.start()

    # Wait for ACPI broadcast to finish issuing (fast, capped internally
    # by libvirt). Then start the drain poll.
    acpi_thread.join(timeout=5.0)
    if acpi_thread.is_alive():
        log.warning("ACPI broadcast still running after 5s — continuing anyway")

    wait_for_shutdown(GUEST_SHUTDOWN_TIMEOUT)
    destroy_remaining_parallel()
    reset_mdevs_on_all_gpus()

    # Join the API call. Should have returned by now; bounded wait.
    api_thread.join(timeout=max(0.5, API_DELETE_TIMEOUT))
    if api_thread.is_alive():
        log.warning("api DELETE thread still running at exit — abandoning")

    log.info("done in %.1fs", time.monotonic() - t_start)


if __name__ == "__main__":
    try:
        run_shutdown()
    except Exception:
        log.error("uncaught exception in shutdown:\n%s", traceback.format_exc())
    # Explicit exit 0 — the trap in start.sh also does `exit 0` but being
    # defensive in case someone runs this standalone.
    sys.exit(0)
