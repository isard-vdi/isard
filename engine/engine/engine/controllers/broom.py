# Copyright 2018 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from time import sleep, time

from engine.config import POLLING_INTERVAL_TRANSITIONAL_STATES
from engine.models.hyp import hyp
from engine.services.db import (
    get_degraded_hyp_ids,
    get_domain_status,
    get_domains_with_transitional_status,
    get_hyp_hostname_from_id,
    get_hyp_hostnames_online,
    update_domain_hyp_started,
    update_domain_status,
    update_hyp_degraded_status,
    update_hyp_libvirt_warning,
    update_table_dict,
    update_table_field,
    update_vgpu_info_if_stopped,
)
from engine.services.lib.functions import get_tid
from engine.services.log import logs
from tabulate import tabulate

# =============================================================================
# Broom Concurrency Configuration
# =============================================================================

# Timeout in seconds for checking a single hypervisor
BROOM_HYP_TIMEOUT = 30

# Maximum number of concurrent hypervisor checks
BROOM_MAX_WORKERS = 20


def format_broom_data(data):
    if data[-1]["time"] > 5:
        print(tabulate(data, headers="keys", tablefmt="grid"))
    current_time = (
        datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()
    )
    print({"time": current_time, "broom_time": data[-1]["time"]})


def _check_single_hypervisor(hyp_id, disk_interval, DB_DOMAINS_ID_STARTED_WITH_HYP):
    """Check a single hypervisor for domain status.

    This function is designed to be called concurrently from a ThreadPoolExecutor.
    It connects to the hypervisor, gets domain status, and handles any issues.

    Args:
        hyp_id: The hypervisor ID to check
        disk_interval: Current disk interval counter for storage updates
        DB_DOMAINS_ID_STARTED_WITH_HYP: Set of domain IDs that have hyp_started set

    Returns:
        dict with keys:
            - hyp_id: The hypervisor ID
            - success: True if check succeeded
            - active_domains: Dict of domain_id -> status_and_detail (if success)
            - domains_destroyed: List of domains destroyed
            - domains_handled: List of domains handled
            - error: Error message (if not success)
    """
    result = {
        "hyp_id": hyp_id,
        "success": False,
        "active_domains": {},
        "domains_destroyed": [],
        "domains_handled": [],
        "error": None,
    }

    try:
        # Get hypervisor connection info
        hyp_info = get_hyp_hostname_from_id(hyp_id)
        if hyp_info is None or hyp_info[0] is False:
            result["error"] = f"hyp {hyp_id} has no hostname or is not in database"
            logs.broom.error(result["error"])
            return result

        (
            hostname,
            port,
            user,
            nvidia_enabled,
            force_get_hyp_info,  # DEPRECATED: ignored
            init_vgpu_profiles,
        ) = hyp_info

        # Connect to hypervisor
        h = hyp(hyp_id, hostname, user=user, port=port)
        if not h.connected:
            result["error"] = f"HYPERVISOR {hyp_id} libvirt connection failed"
            logs.broom.error(result["error"])
            return result

        try:
            # Update storage usage if needed
            if disk_interval == 1:
                update_table_dict(
                    "hypervisors",
                    hyp_id,
                    {"mountpoints": h.get_storage_used()},
                    soft=True,
                )

            # Get domains from hypervisor
            d_domains_status_from_hyp = h.get_domains()
            if d_domains_status_from_hyp is None:
                d_domains_status_from_hyp = {}

            # Check domains running in hypervisor that are not in database
            for domain_id, status_and_detail in d_domains_status_from_hyp.items():
                if domain_id not in DB_DOMAINS_ID_STARTED_WITH_HYP:
                    domain_status = get_domain_status(domain_id)
                    if domain_status is None:
                        try:
                            domain_handler = h.conn.lookupByName(domain_id)
                            domain_handler.destroy()
                            result["domains_destroyed"].append(domain_id)
                            logs.broom.error(
                                f"broom destroyed domain not in database {domain_id} in hypervisor {hyp_id}"
                            )
                        except Exception as e:
                            logs.broom.error(
                                f"EXCEPTION when try to destroy domain not in database {domain_id} in hypervisor {hyp_id} with exception: {e}"
                            )
                        continue

                    if domain_status not in [
                        "Started",
                        "Paused",
                        "Shutting-down",
                        "Stopping",
                        "Deleting",
                        "ForceDeleting",
                        "CreatingDomain",
                        "CreatingAndStarting",
                        "CreatingDiskFromScratch",
                        "StartingDomainDisposable",
                    ]:
                        logs.broom.warning(
                            f"broom find domain {domain_id} with status {domain_status} started in hypervisor {hyp_id} and updated status and hyp_started in database"
                        )
                        update_domain_hyp_started(
                            domain_id,
                            hyp_id,
                            "hyp_started updated by broom",
                            "Started",
                        )
                    result["domains_handled"].append(domain_id)

            # Remove destroyed and handled domains from result
            for k in result["domains_destroyed"]:
                d_domains_status_from_hyp.pop(k, None)
            for k in result["domains_handled"]:
                d_domains_status_from_hyp.pop(k, None)

            result["active_domains"] = d_domains_status_from_hyp
            result["success"] = True

        finally:
            h.disconnect()

    except Exception as e:
        result["error"] = str(e)
        logs.exception_id.debug("0003")
        logs.broom.error(f"Exception when try to hypervisor {hyp_id}: {e}")
        logs.broom.error(f"Traceback: {traceback.format_exc()}")

    return result


class ThreadBroom(threading.Thread):
    def __init__(self, name, polling_interval, manager):
        threading.Thread.__init__(self)
        self.manager = manager
        self.name = name
        self.polling_interval = polling_interval
        self.stop = False
        self._executor = ThreadPoolExecutor(
            max_workers=BROOM_MAX_WORKERS, thread_name_prefix="broom_hyp_check"
        )
        # Track which hypervisors the broom has marked as degraded
        self._broom_degraded_hyps = set()

    def stop_thread(self):
        """Stop the broom thread and cleanup resources."""
        self.stop = True
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass

    def _check_hypervisors_concurrent(
        self, hyp_ids, disk_interval, DB_DOMAINS_ID_STARTED_WITH_HYP
    ):
        """Check multiple hypervisors concurrently.

        Args:
            hyp_ids: List of hypervisor IDs to check
            disk_interval: Current disk interval counter
            DB_DOMAINS_ID_STARTED_WITH_HYP: Set of domain IDs with hyp_started set

        Returns:
            dict mapping hyp_id -> {"active_domains": {...}} for successful checks
        """
        hyps_domain_started = {}

        if not hyp_ids:
            return hyps_domain_started

        # Submit all hypervisor checks concurrently
        futures = {
            self._executor.submit(
                _check_single_hypervisor,
                hyp_id,
                disk_interval,
                DB_DOMAINS_ID_STARTED_WITH_HYP,
            ): hyp_id
            for hyp_id in hyp_ids
        }

        # Collect results with overall timeout
        failed_hyps = set()
        succeeded_hyps = set()
        try:
            for future in as_completed(futures, timeout=BROOM_HYP_TIMEOUT + 5):
                hyp_id = futures[future]
                try:
                    result = future.result(timeout=1)
                    if result["success"]:
                        hyps_domain_started[hyp_id] = {
                            "active_domains": result["active_domains"]
                        }
                        succeeded_hyps.add(hyp_id)
                    else:
                        failed_hyps.add(hyp_id)
                        logs.broom.warning(
                            f"Hypervisor {hyp_id} check failed: {result.get('error', 'unknown')}"
                        )
                except Exception as e:
                    failed_hyps.add(hyp_id)
                    logs.broom.error(
                        f"Exception getting result for hypervisor {hyp_id}: {e}"
                    )
        except TimeoutError:
            # Some hypervisors timed out, log which ones
            for future, hyp_id in futures.items():
                if not future.done():
                    failed_hyps.add(hyp_id)
                    logs.broom.warning(
                        f"Hypervisor {hyp_id} check timed out after {BROOM_HYP_TIMEOUT + 5}s"
                    )

        # Mark failed hypervisors as degraded
        for hyp_id in failed_hyps:
            if hyp_id not in self._broom_degraded_hyps:
                try:
                    update_hyp_degraded_status(
                        hyp_id,
                        is_degraded=True,
                        reason="broom connectivity check failed",
                    )
                    self._broom_degraded_hyps.add(hyp_id)
                except Exception as e:
                    logs.broom.error(
                        f"Failed to mark hypervisor {hyp_id} as degraded: {e}"
                    )

        # Recover hypervisors that were degraded by broom but now succeed
        recovered = self._broom_degraded_hyps & succeeded_hyps
        for hyp_id in recovered:
            try:
                update_hyp_degraded_status(hyp_id, is_degraded=False)
                update_hyp_libvirt_warning(hyp_id, clear=True)
                self._broom_degraded_hyps.discard(hyp_id)
                logs.broom.info(
                    f"Hypervisor {hyp_id} recovered from broom-detected degraded state"
                )
            except Exception as e:
                logs.broom.error(
                    f"Failed to recover hypervisor {hyp_id} from degraded: {e}"
                )

        # Also recover hyps degraded by other components (e.g. worker thread
        # from a previous session) that now pass the connectivity check
        try:
            db_degraded = get_degraded_hyp_ids()
            stale_degraded = (db_degraded & succeeded_hyps) - self._broom_degraded_hyps
            for hyp_id in stale_degraded:
                try:
                    update_hyp_degraded_status(hyp_id, is_degraded=False)
                    update_hyp_libvirt_warning(hyp_id, clear=True)
                    logs.broom.info(
                        f"Hypervisor {hyp_id} recovered from stale degraded state"
                    )
                except Exception as e:
                    logs.broom.error(
                        f"Failed to recover hypervisor {hyp_id} from stale degraded: {e}"
                    )
        except Exception as e:
            logs.broom.error(f"Failed to query degraded hypervisors: {e}")

        return hyps_domain_started

    def polling(self):
        disk_interval = 0
        while self.stop is not True:
            try:
                interval = 0.0
                while interval < self.polling_interval:
                    sleep(0.1)
                    interval += 0.1
                    if self.stop is True:
                        break
                if disk_interval >= 300:
                    disk_interval = 0
                disk_interval += 1
                if self.manager.check_actions_domains_enabled() is False:
                    continue

                t_broom = time()
                t_broom_data = []
                """
                DB DOMAINS TRANSITIONAL STATES
                """
                t_broom_inner = time()
                l = get_domains_with_transitional_status(also_started=True)
                t_broom_data.append(
                    {
                        "step": "get_domains_with_transitional_status",
                        "count": len(l),
                        "time": round(time() - t_broom_inner, 2),
                    }
                )
                t_broom_inner = time()
                DB_DOMAINS_WITHOUT_HYP = [
                    d
                    for d in l
                    if not d.get("hyp_started") or type(d.get("hyp_started")) is bool
                ]
                DB_DOMAINS_STARTED_WITH_HYP = [
                    d
                    for d in l
                    if d.get("hyp_started") and type(d.get("hyp_started")) is not bool
                ]
                DB_DOMAINS_ID_STARTED_WITH_HYP = {
                    a["id"] for a in DB_DOMAINS_STARTED_WITH_HYP
                }
                # ids_domains_started_in_db_without_hypervisor = [
                #     a["id"] for a in DB_DOMAINS_WITHOUT_HYP
                # ]

                t_broom_data.append(
                    {
                        "step": "split_domains_with_transitional_status",
                        "count": len(DB_DOMAINS_WITHOUT_HYP),
                        "time": round(time() - t_broom_inner, 2),
                    }
                )

                t_broom_inner = time()
                for db_domain in DB_DOMAINS_WITHOUT_HYP:
                    if db_domain["status"] in (
                        "Stopping",
                        "Starting",
                        "StartingPaused",
                    ):
                        continue
                    logs.broom.error(
                        "DOMAIN {} WITH STATUS {} without HYPERVISOR".format(
                            db_domain["id"], db_domain["status"]
                        )
                    )
                    update_domain_status(
                        "Unknown",
                        db_domain["id"],
                        detail="starting or stoping status without hypervisor",
                    )
                t_broom_data.append(
                    {
                        "step": "update_domains_without_hypervisor",
                        "count": len(DB_DOMAINS_WITHOUT_HYP),
                        "time": round(time() - t_broom_inner, 2),
                    }
                )

                t_broom_inner = time()
                HYPERS_ONLINE = list(get_hyp_hostnames_online().keys())
                t_broom_data.append(
                    {
                        "step": "get_hyp_hostnames_online",
                        "count": len(HYPERS_ONLINE),
                        "time": round(time() - t_broom_inner, 2),
                    }
                )
                # Check all hypervisors concurrently instead of sequentially
                t_broom_inner = time()
                hyps_domain_started = self._check_hypervisors_concurrent(
                    HYPERS_ONLINE, disk_interval, DB_DOMAINS_ID_STARTED_WITH_HYP
                )
                t_broom_data.append(
                    {
                        "step": "get_domains_from_hypervisors",
                        "count": len(hyps_domain_started),
                        "time": round(time() - t_broom_inner, 2),
                    }
                )
                ## DOMAINS ACTIVE EN HYPERVISOR THAT ARE STOPPED, FAILED, UNKNOWN IN DATABASE...
                for hyp_id, d in hyps_domain_started.items():
                    t_broom_inner = time()
                    if d.get("active_domains"):
                        for domain_id, d_status in d["active_domains"].items():
                            domain_status = d_status["status"]
                            domain_status_detail = d_status["detail"]
                            if domain_id not in DB_DOMAINS_ID_STARTED_WITH_HYP:
                                db_domain_status = get_domain_status(domain_id)
                                if db_domain_status is None:
                                    logs.broom.error(
                                        "CRITICAL, if domain is not in database, must have been destroyed previously by broom, will do it next loop"
                                    )
                                    continue
                                if db_domain_status in [
                                    "CreatingDomain",
                                    "CreatingAndStarting",
                                    "CreatingDiskFromScratch",
                                    "StartingDomainDisposable",
                                ]:
                                    logs.broom.debug(
                                        f"broom skipping domain {domain_id} in creation status {db_domain_status} on hypervisor {hyp_id}"
                                    )
                                    continue
                                if domain_status == "Started":
                                    logs.broom.error(
                                        f"broom find domain {domain_id} with status {domain_status} in hypervisor {hyp_id} and updated status and hyp_started in databse"
                                    )
                                    if db_domain_status not in ["ForceDeleting"]:
                                        update_domain_hyp_started(
                                            domain_id,
                                            hyp_id,
                                            "State and hyp_started updated by broom",
                                            domain_status,
                                        )
                                elif domain_status == "Paused":
                                    if domain_status_detail == "paused on user request":
                                        logs.broom.error(
                                            f"broom find domain {domain_id} with status {domain_status} with detail {domain_status_detail} in hypervisor {hyp_id} and updated status and hyp_started in databse"
                                        )
                                        if db_domain_status not in [
                                            "Stopped",
                                            "ForceDeleting",
                                        ]:
                                            update_domain_hyp_started(
                                                domain_id,
                                                hyp_id,
                                                "State and hyp_started updated by broom",
                                                domain_status,
                                            )
                                    else:
                                        logs.broom.info(
                                            f"broom find domain {domain_id} with status {domain_status} in hypervisor {hyp_id} with detail {domain_status_detail} , domain starting-paused?"
                                        )
                                else:
                                    logs.broom.error(
                                        f"CRITICAL: STATUS FROM LIBVIRT IS NOT STARTED OR PAUSED!! broom find domain {domain_id} with status {domain_status} in hypervisor {hyp_id}"
                                    )
                                    logs.broom.error(
                                        f"CRITICAL: broom not update strange status {domain_id} with status {domain_status} in hypervisor {hyp_id}"
                                    )
                    t_broom_data.append(
                        {
                            "step": f"update_domains_from_hypervisors {hyp_id}",
                            "count": len(hyps_domain_started),
                            "time": round(time() - t_broom_inner, 2),
                        }
                    )

                t_broom_inner = time()
                for d in DB_DOMAINS_WITHOUT_HYP:
                    domain_id = d["id"]
                    status = d["status"]
                    if status == "Stopping":
                        logs.broom.debug(
                            "DOMAIN: {} STATUS STOPPING WITHOUTH HYPERVISOR, UNKNOWN REASON".format(
                                domain_id
                            )
                        )
                        update_domain_status(
                            "Stopped",
                            domain_id,
                            detail="Stopped by broom thread because has not hypervisor",
                        )
                t_broom_data.append(
                    {
                        "step": "update_domains_without_hypervisor",
                        "count": len(DB_DOMAINS_WITHOUT_HYP),
                        "time": round(time() - t_broom_inner, 2),
                    }
                )

                t_broom_inner = time()
                for d in DB_DOMAINS_STARTED_WITH_HYP:
                    domain_id = d["id"]
                    status = d["status"]
                    hyp_started = d["hyp_started"]
                    if type(hyp_started) is bool:
                        continue
                    if len(hyp_started) == 0:
                        continue
                    # TODO bug sometimes hyp_started not in hyps_domain_started keys... why?
                    if (
                        hyp_started in hyps_domain_started.keys()
                        and len(hyp_started) > 0
                    ):
                        if status == "Started":
                            pass
                        elif status == "Starting":
                            logs.broom.debug(
                                "DOMAIN: {} STATUS STARTING TO RUN IN HYPERVISOR: {}".format(
                                    domain_id, hyp_started
                                )
                            )
                            if (
                                domain_id
                                in hyps_domain_started[hyp_started]["active_domains"]
                            ):
                                logs.broom.debug(
                                    "DOMAIN: {} ACTIVE IN HYPERVISOR: {}".format(
                                        domain_id, hyp_started
                                    )
                                )
                                active_status = hyps_domain_started[hyp_started][
                                    "active_domains"
                                ][domain_id]["status"]
                                logs.broom.debug(
                                    "DOMAIN: {} ACTIVE IN HYPERVISOR: {} WITH STATUS: {}".format(
                                        domain_id, hyp_started, active_status
                                    )
                                )
                                update_domain_hyp_started(domain_id, hyp_started)
                            else:
                                logs.broom.debug(
                                    "DOMAIN: {} NOT ACTIVE YET IN HYPERVISOR: {} ".format(
                                        domain_id, hyp_started
                                    )
                                )
                        elif status == "Stopping":
                            logs.broom.debug(
                                "DOMAIN: {} STATUS STOPPING IN HYPERVISOR: {}".format(
                                    domain_id, hyp_started
                                )
                            )
                            if (
                                domain_id
                                not in hyps_domain_started[hyp_started][
                                    "active_domains"
                                ]
                            ):
                                update_domain_status(
                                    "Stopped",
                                    domain_id,
                                    detail="Stopped by broom thread",
                                )
                                update_vgpu_info_if_stopped(domain_id)
                        elif status == "Resetting":
                            if int(time()) - int(d["accessed"]) > 60:
                                logs.broom.debug(
                                    "DOMAIN: {} STATUS RESETTING IN HYPERVISOR: {}".format(
                                        domain_id, hyp_started
                                    )
                                )
                                update_domain_status(
                                    "Failed",
                                    domain_id,
                                    detail="Failed from Resetting state by broom thread",
                                )
                        elif status == "Shutting-down":
                            logs.broom.debug(
                                "DOMAIN: {} STATUS Shutting-down IN HYPERVISOR: {}".format(
                                    domain_id, hyp_started
                                )
                            )
                            if int(time()) - int(d["accessed"]) > 5 * 60:
                                update_domain_status(
                                    "Stopping",
                                    domain_id,
                                    keep_hyp_id=True,
                                    detail="Stopping by broom thread",
                                )
                                logs.broom.info(
                                    f"domain {domain_id} updated to Stopping after 5 min in Shutting-down"
                                )
                        else:
                            logs.broom.info(
                                "DOMAIN with status {}: {} NOT ACTIVE YET IN HYPERVISOR: {} ?".format(
                                    status, domain_id, hyp_started
                                )
                            )
                    else:
                        if len(hyps_domain_started) > 0:
                            logs.broom.error(
                                "domain {} has an hyp_started: {} NOT IN hyps_domain_started keys:".format(
                                    domain_id, hyp_started
                                )
                            )
                t_broom_data.append(
                    {
                        "step": "update_domains_with_hypervisor",
                        "count": len(DB_DOMAINS_STARTED_WITH_HYP),
                        "time": round(time() - t_broom_inner, 2),
                    }
                )
                t_broom_data.append(
                    {
                        "step": "total",
                        "count": "-",
                        "time": round(time() - t_broom, 2),
                    }
                )
                format_broom_data(t_broom_data)
            except Exception as e:
                logs.broom.error(
                    "Exception in broom thread. Traceback: {}".format(
                        traceback.format_exc()
                    )
                )

    def run(self):
        self.tid = get_tid()
        logs.broom.info("starting thread: {} (TID {})".format(self.name, self.tid))
        self.polling()


def launch_thread_broom(manager):
    t = ThreadBroom(
        name="broom",
        polling_interval=POLLING_INTERVAL_TRANSITIONAL_STATES,
        manager=manager,
    )
    t.daemon = True
    t.start()
    return t
