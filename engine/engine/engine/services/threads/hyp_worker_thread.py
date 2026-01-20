# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import base64
import queue
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pprint import pformat

from engine.models.domain_xml import DomainXML
from engine.models.hyp import hyp
from engine.services.db import (
    get_hyp_hostname_from_id,
    get_hyp_status,
    get_hyp_viewer_info,
    get_table_field,
    update_db_hyp_info,
    update_domain_status,
    update_domain_viewer_started_values,
    update_domains_started_in_hyp_to_unknown,
    update_hyp_status,
    update_last_hyp_id,
    update_table_field,
    update_vgpu_info_if_stopped,
    update_vgpu_uuid_domain_action,
)
from engine.services.db.hypervisors import update_hyp_thread_status
from engine.services.lib.functions import (
    SSHTimeoutError,
    exec_remote_list_of_cmds_dict,
    get_tid,
    update_status_db_from_running_domains,
)
from engine.services.lib.qmp import Notifier, PersonalUnit
from engine.services.log import logs
from engine.services.threads.threads import (
    RETRIES_HYP_IS_ALIVE,
    TIMEOUT_BETWEEN_RETRIES_HYP_IS_ALIVE,
    TIMEOUT_QUEUES,
    launch_action_disk,
    launch_delete_media,
    launch_killall_curl,
)
from isardvdi_common.api_rest import ApiRest
from libvirt import (
    VIR_DOMAIN_SHUTDOWN_ACPI_POWER_BTN,
    VIR_DOMAIN_START_PAUSED,
    VIR_ERR_NO_DOMAIN,
    libvirtError,
)
from requests.exceptions import ReadTimeout as requests_ReadTimeout

api_client = ApiRest("isard-api")


ITEMS_STATUS_MAP = {
    "start_paused_domain": "Checking",
    "start_domain": "Starting",
    "shutdown_domain": "Shutting down",
    "stop_domain": "Stopping",
    "reset_domain": "Starting",
    "create_disk": "Creating disk",
    "delete_disk": "Deleting disk",
    "add_media_hot": "Adding media",
    "killall_curl": "Canceling download",
    "delete_media": "Deleting media",
}

notify_thread_pool = ThreadPoolExecutor(max_workers=1)


def notify_desktop_in_thread(domain, message):
    try:
        Notifier.notify_desktop(domain, message)
    except Exception as error:
        logs.workers.debug(
            f'Error notifying desktop {domain.name()} with "{base64.b64decode(message).decode()}": {error}'
        )
        raise error


NOTIFY_PERSONAL_UNIT = False

if NOTIFY_PERSONAL_UNIT:
    personal_unit_thread_pool = ThreadPoolExecutor(max_workers=1)

    def personal_unit_in_thread(domain):
        try:
            PersonalUnit.connect_personal_unit(domain)
        except Exception as error:
            logs.workers.debug(
                f"Error connecting personal unit for desktop {domain.name()}: {error}"
            )
            raise error


def log_action(
    hyp_id, id_domain, action, intervals, total_time, final_status, log_level="info"
):
    log_data = {
        "hyp_id": hyp_id,
        "desktop_id": id_domain,
        "action": action,
        "total_time": total_time,
        "final_status": final_status,
        "intervals": intervals,
    }
    if log_level == "info":
        logs.workers.info(f"{log_data}")
    elif log_level == "warning":
        logs.workers.warning(f"{log_data}")
    else:
        logs.workers.error(f"{log_data}")


class HypWorkerThread(threading.Thread):
    def __init__(self, name, hyp_id, queue_actions, q_event_register, queue_master):
        threading.Thread.__init__(self)
        self.name = name
        self.hyp_id = hyp_id
        self.stop = False
        self.queue_actions = queue_actions
        self.queue_master = queue_master
        self.q_event_register = q_event_register
        self.h = False
        self.error = False
        self.viewer = get_hyp_viewer_info(hyp_id)
        self.last_api_call_time = time.time()
        self.hostname = None
        self.current_action = {}

    def run(self):
        """Main thread execution method"""
        try:
            self._initialize()
            if self.stop:
                return

            self._main_loop()
        except Exception as e:
            logs.workers.error(f"Unhandled exception in worker thread: {e}")
            logs.workers.error(traceback.format_exc())
        finally:
            self._cleanup()

    def _initialize(self):
        """Initialize the worker thread and hypervisor connection"""
        self.tid = get_tid()
        logs.workers.info(f"Starting thread: {self.name} (TID {self.tid})")

        # Get hypervisor connection parameters
        host_info = get_hyp_hostname_from_id(self.hyp_id)
        if not host_info or host_info[0] is False:
            self._set_error("Hostname not in database")
            return

        host, port, user, nvidia_enabled, force_get_hyp_info, init_vgpu_profiles = (
            host_info
        )
        port = int(port)
        self.hostname = host

        # Connect to hypervisor
        if not self._establish_connection(host, port, user, nvidia_enabled):
            return

        # Test SSH connectivity
        if not self._test_ssh_connection(host, port, user):
            return

        # Get hypervisor info
        if not self._initialize_hypervisor_info(
            nvidia_enabled, force_get_hyp_info, init_vgpu_profiles
        ):
            return

        # All initialization successful - set hypervisor online first
        update_table_field("hypervisors", self.hyp_id, "stats", self.h.stats, soft=True)
        update_hyp_status(self.hyp_id, "Online")

        # Certificate expiration check disabled - was causing startup delays
        # try:
        #     update_table_field(
        #         "hypervisors",
        #         self.hyp_id,
        #         "viewer_status",
        #         self.h.get_hyp_video_status(),
        #         soft=True,
        #     )
        # except Exception as e:
        #     logs.workers.warning(
        #         f"Failed to update viewer status for {self.hyp_id}: {e}"
        #     )

    def _establish_connection(self, host, port, user, nvidia_enabled):
        """Establish connection to the hypervisor"""
        try:
            self.h = hyp(
                self.hyp_id,
                host,
                user=user,
                port=port,
                nvidia_enabled=nvidia_enabled,
            )

            if not self.h.conn:
                self._set_error("Cannot connect to libvirt")
                return False

            if self.h.conn.isAlive() != 1:
                self._set_error("Libvirt connection is not alive")
                return False

            return True
        except Exception as e:
            logs.exception_id.debug("0059")
            self._set_error(f"Exception during hypervisor connection: {e}")
            return False

    def _test_ssh_connection(self, host, port, user):
        """Test SSH connection to the hypervisor"""
        logs.workers.info(f"[{self.hyp_id}] Testing SSH connection to {host}:{port}...")
        cmds = [{"cmd": "uname -a"}]
        try:
            array_out_err = exec_remote_list_of_cmds_dict(
                host, cmds, username=user, port=port, timeout=30
            )
            output = array_out_err[0]["out"]
            logs.main.debug(f"Command: {cmds[0]}, output: {output}")

            if not output:
                self._set_error("SSH command output is empty, SSH action failed")
                return False

            logs.workers.info(f"[{self.hyp_id}] SSH test passed")

            # SSH test passed
            launch_killall_curl(self.hostname, user, port)
            self.h.update_domain_coherence_in_db()
            update_hyp_thread_status("worker", self.hyp_id, "Started")

            # Register for events
            self.q_event_register.put(
                {
                    "type": "add_hyp_to_receive_events",
                    "hyp_id": self.hyp_id,
                    "worker": self,
                }
            )
            return True

        except SSHTimeoutError as e:
            logs.workers.error(f"[{self.hyp_id}] SSH connection test timed out: {e}")
            self._set_error(f"SSH connection test timed out: {e}")
            return False
        except Exception as e:
            logs.exception_id.debug("0058")
            self._set_error(f"Testing SSH connection failed: {e}")
            return False

    def _initialize_hypervisor_info(
        self, nvidia_enabled, force_get_hyp_info, init_vgpu_profiles
    ):
        """Initialize hypervisor information

        Note: force_get_hyp_info parameter is DEPRECATED and ignored.
        GPU hardware changes are now auto-detected by the engine.
        """
        logs.workers.info(
            f"[{self.hyp_id}] Starting hypervisor info initialization "
            f"(nvidia_enabled={nvidia_enabled})"
        )
        if force_get_hyp_info:
            logs.workers.warning(
                f"[{self.hyp_id}] DEPRECATED: force_get_hyp_info is set but ignored. "
                f"GPU hardware changes are now auto-detected."
            )
        try:
            # Step 1: Get info from hypervisor
            logs.workers.info(
                f"[{self.hyp_id}] Step 1/4: Getting info from hypervisor..."
            )
            step_start = time.time()
            # Note: force_get_hyp_info is passed but ignored by get_info_from_hypervisor()
            self.h.get_info_from_hypervisor(
                nvidia_enabled=nvidia_enabled,
                force_get_hyp_info=False,  # Always pass False - auto-detection handles this
                init_vgpu_profiles=init_vgpu_profiles,
            )
            logs.workers.info(
                f"[{self.hyp_id}] Step 1/4: get_info_from_hypervisor completed in {time.time() - step_start:.2f}s"
            )

            # Step 2: Get system stats
            logs.workers.info(f"[{self.hyp_id}] Step 2/4: Getting system stats...")
            step_start = time.time()
            self.h.get_system_stats()
            logs.workers.info(
                f"[{self.hyp_id}] Step 2/4: get_system_stats completed in {time.time() - step_start:.2f}s"
            )

            # Step 3: Load info from database
            logs.workers.info(
                f"[{self.hyp_id}] Step 3/4: Loading info from database..."
            )
            step_start = time.time()
            self.h.load_info_from_db()
            logs.workers.info(
                f"[{self.hyp_id}] Step 3/4: load_info_from_db completed in {time.time() - step_start:.2f}s"
            )

            # Step 4: Initialize NVIDIA if enabled
            if nvidia_enabled:
                logs.workers.info(
                    f"[{self.hyp_id}] Step 4/4: Initializing NVIDIA GPU support..."
                )
                step_start = time.time()
                self.h.init_nvidia()
                logs.workers.info(
                    f"[{self.hyp_id}] Step 4/4: init_nvidia completed in {time.time() - step_start:.2f}s"
                )
            else:
                logs.workers.info(
                    f"[{self.hyp_id}] Step 4/4: Skipping NVIDIA init (not enabled)"
                )

            # Check virtualization support
            if self.h.info["kvm_module"] not in ["intel", "amd"]:
                logs.workers.error(
                    f"Hypervisor {self.hyp_id} has no virtualization support"
                )
                update_hyp_status(
                    self.hyp_id,
                    "Error",
                    detail="KVM requires virtualization support (VT-x for Intel or AMD-V for AMD). "
                    "Check CPU capabilities and enable virtualization in BIOS.",
                )
                self.stop = True
                return False

            logs.workers.info(
                f"[{self.hyp_id}] Hypervisor info initialization completed successfully"
            )
            return True

        except SSHTimeoutError as e:
            logs.workers.error(
                f"[{self.hyp_id}] SSH timeout during hypervisor initialization: {e}"
            )
            self._set_error(f"SSH timeout during initialization: {e}")
            return False
        except Exception as e:
            logs.exception_id.debug("0059")
            logs.workers.error(
                f"[{self.hyp_id}] Failed to get hypervisor info: {e}\n{traceback.format_exc()}"
            )
            self._set_error(f"Failed to get hypervisor info: {e}")
            return False

    def _set_error(self, error_msg):
        """Set error state and update hypervisor status"""
        self.error = error_msg
        update_hyp_status(self.hyp_id, "Error", detail=error_msg)
        self.stop = True

    def _main_loop(self):
        """Main processing loop for actions"""
        last_stats_update = time.time()

        while not self.stop:
            action = {}
            intervals = []
            action_time = time.time()

            try:
                # Process actions from queue
                action = self.queue_actions.get(timeout=TIMEOUT_QUEUES)
                self.current_action = action
                action_time = time.time()

                # Process the action
                self._process_action(action, action_time, intervals)

            except queue.Empty:
                # No actions in queue, check connection
                self._check_connection(action_time, intervals)
            except Exception as e:
                logs.workers.error(
                    f"Error processing action {action.get('type', 'unknown')}: {e}"
                )
                logs.workers.error(traceback.format_exc())
                self._handle_action_error(action, e, action_time, intervals)

            # Reset current action
            self.current_action = {}

            # Update stats if necessary
            self._update_stats_if_needed(
                action, action_time, intervals, last_stats_update
            )
            last_stats_update = (
                time.time()
                if time.time() - last_stats_update > 10
                else last_stats_update
            )

    def _process_action(self, action, action_time, intervals):
        """Process an action based on its type"""
        action_type = action.get("type", "unknown")
        action_handlers = {
            "start_paused_domain": self._handle_start_paused_domain,
            "start_domain": self._handle_start_domain,
            "shutdown_domain": self._handle_shutdown_domain,
            "stop_domain": self._handle_stop_domain,
            "reset_domain": self._handle_reset_domain,
            "create_disk": lambda a, t, i: self._handle_disk_action(a, t, i, "create"),
            "delete_disk": lambda a, t, i: self._handle_disk_action(a, t, i, "delete"),
            "add_media_hot": lambda a, t, i: None,  # Placeholder as in original
            "killall_curl": self._handle_killall_curl,
            "delete_media": self._handle_delete_media,
            "update_status_db_from_running_domains": self._handle_update_status,
            "hyp_info": self._handle_hyp_info,
            "notify": self._handle_notify,
            "personal_unit": self._handle_personal_unit,
            "stop_thread": lambda a, t, i: setattr(self, "stop", True),
        }

        handler = action_handlers.get(action_type)
        if handler:
            handler(action, action_time, intervals)
        else:
            logs.workers.error(f"Unsupported action type: {action_type}")

        # Update desktop queue if appropriate
        if action_type in ITEMS_STATUS_MAP:
            self._update_queue_for_action(action, action_time, intervals)

    def _update_queue_for_action(self, action, action_time, intervals):
        """Update the desktop queue after processing an action"""
        try:
            t = time.time()
            self.update_desktops_queue()
            intervals.append({"update_desktops_queue": round(time.time() - t, 3)})
            log_action(
                self.hyp_id,
                action.get("id_domain"),
                action["type"],
                intervals,
                time.time() - action_time,
                ITEMS_STATUS_MAP[action["type"]],
            )
        except Exception as e:
            logs.workers.error(f"Error sending desktops queue to API: {e}")

    def _handle_action_error(self, action, exception, action_time, intervals):
        """Handle errors that occur during action processing"""
        if action.get("id_domain"):
            update_domain_status(
                "Failed",
                action["id_domain"],
                hyp_id=self.hyp_id,
                detail=f"Error: {exception}",
            )
            log_action(
                self.hyp_id,
                action["id_domain"],
                action.get("type", "unknown"),
                intervals,
                time.time() - action_time,
                "Failed",
            )

    def _update_stats_if_needed(
        self, action, action_time, intervals, last_stats_update
    ):
        """Update hypervisor stats if needed"""
        current_time = time.time()
        if (
            action.get("type") in ["start_domain", "stop_domain"]
            or current_time - last_stats_update > 10
        ):
            try:
                t = time.time()
                self.h.get_system_stats()
                intervals.append({"get_system_stats": round(time.time() - t, 3)})

                stats = self.h.stats
                if action.get("type") in ["start_domain", "stop_domain"]:
                    stats["last_action"] = {
                        "timestamp": current_time,
                        "action": action.get("type"),
                        "action_time": current_time - action_time,
                        "intervals": intervals,
                    }
                    stats["positioned_items"] = self.get_positioned_items()

                update_table_field(
                    "hypervisors", self.hyp_id, "stats", stats, soft=True
                )
                logs.workers.debug(f"Hypervisor {self.hyp_id} stats updated")
            except Exception as e:
                logs.workers.error(f"Failed to update hypervisor stats: {e}")

    def _check_connection(self, action_time, intervals):
        """Check if connection is alive"""
        try:
            t = time.time()
            self.h.conn.isAlive()
            intervals.append({"libvirt isAlive": round(time.time() - t, 3)})

            if time.time() - t > 1:
                log_action(
                    self.hyp_id,
                    None,
                    "libvirt_isAlive",
                    intervals,
                    time.time() - action_time,
                    "Finished, but took too long",
                    "warning",
                )
        except Exception:
            logs.workers.info(
                f"Connection test failed for hypervisor {self.hostname}, attempting to reconnect"
            )
            self._try_reconnect()

    def _try_reconnect(self):
        """Try to reconnect to the hypervisor"""
        host = self.hostname
        alive = False

        # Try multiple reconnection attempts
        for i in range(RETRIES_HYP_IS_ALIVE):
            logs.workers.info(
                f"Retry hypervisor connection {i+1}/{RETRIES_HYP_IS_ALIVE}"
            )
            try:
                time.sleep(TIMEOUT_BETWEEN_RETRIES_HYP_IS_ALIVE)
                self.h.conn.getLibVersion()
                alive = True
                logs.workers.info(f"Hypervisor {host} is alive")
                break
            except Exception as e:
                logs.exception_id.debug("0066")
                logs.workers.info(f"Hypervisor {host} is NOT alive. Exception: {e}")

        if not alive:
            self._handle_failed_reconnection()

    def _handle_failed_reconnection(self):
        """Handle case where reconnection fails"""
        try:
            # Try one last full reconnection
            self.h.connect_to_hyp()
            self.h.conn.getLibVersion()
            # Update domain status
            self.h.update_domain_coherence_in_db()
            update_hyp_status(self.hyp_id, "Online")
        except Exception:
            logs.workers.error(f"Failed to reconnect to hypervisor {self.hostname}")

            # Update hypervisor status
            reason = getattr(self.h, "fail_connected_reason", "Connection failed")
            status = get_hyp_status(self.hyp_id)
            if status == "Online":
                update_hyp_status(self.hyp_id, "Error", reason)

            # Mark domains as unknown
            update_domains_started_in_hyp_to_unknown(self.hyp_id)

            logs.workers.error(
                f"Worker thread for hypervisor {self.hyp_id} exiting due to error"
            )
            self.error = True
            self.stop = True

    def _cleanup(self):
        """Clean up resources before thread termination"""
        try:
            update_hyp_thread_status("worker", self.hyp_id, "Stopping")

            # Disconnect from hypervisor
            if self.h:
                try:
                    self.h.disconnect()
                except Exception as e:
                    logs.exception_id.debug("0066")
                    logs.workers.error(
                        f"Unable to disconnect from hypervisor {self.hyp_id}: {e}"
                    )

            # Remove from event registry
            self.q_event_register.put(
                {"type": "del_hyp_to_receive_events", "hyp_id": self.hyp_id}
            )

            # Notify master thread
            self.queue_master.put(
                {"type": "thread_hyp_worker_dead", "hyp_id": self.hyp_id}
            )

        except Exception as e:
            logs.exception_id.debug("0067")
            logs.workers.error(f"Error in cleanup for hypervisor {self.hyp_id}: {e}")

    def _lookup_domain(self, action, intervals, action_name="lookup"):
        """Common method to look up a domain by name"""
        try:
            lt = time.time()
            domain = self.h.conn.lookupByName(action["id_domain"])
            intervals.append(
                {f"conn.lookupByName for {action_name}": round(time.time() - lt, 3)}
            )
            return domain, None
        except libvirtError as e:
            return None, e
        except Exception as e:
            return None, e

    def _handle_libvirt_error(self, action, e, action_time, intervals, operation):
        """Handle common libvirt errors"""
        error_msg = str(e)
        if isinstance(e, libvirtError):
            error_msg = e.get_error_message()

        if "internal error: client socket is closed" in error_msg:
            # Connection lost - mark hypervisor as failed
            update_hyp_status(self.hyp_id, "Error", detail=error_msg)
            self.stop = True
            update_domains_started_in_hyp_to_unknown(self.hyp_id)
            return

        if e.get_error_code() == VIR_ERR_NO_DOMAIN and operation == "stop":
            # Domain already undefined - this is OK for stop operations
            return False

        # Normal error handling
        update_domain_status(
            "Failed",
            action["id_domain"],
            hyp_id=self.hyp_id,
            detail=f"Error during {operation}: {error_msg}",
        )
        logs.workers.error(
            f"LibvirtError in {operation} for domain {action['id_domain']}: {error_msg}"
        )
        log_action(
            self.hyp_id,
            action["id_domain"],
            action["type"],
            intervals,
            time.time() - action_time,
            "Failed",
        )
        return True

    # Action handlers
    def _handle_start_paused_domain(self, action, action_time, intervals):
        """Handle start_paused_domain action"""
        logs.workers.debug(f"XML to start paused domain: {action['xml'][30:100]}")

        try:
            # Create domain in paused state
            lt = time.time()
            self.h.conn.createXML(action["xml"], flags=VIR_DOMAIN_START_PAUSED)
            intervals.append({"libvirt createXML paused": round(time.time() - lt, 3)})

            # Check for paused domains
            FLAG_LIST_DOMAINS_PAUSED = 32
            lt = time.time()
            list_all_domains = self.h.conn.listAllDomains(FLAG_LIST_DOMAINS_PAUSED)
            intervals.append(
                {"libvirt listAllDomains(paused)": round(time.time() - lt, 3)}
            )

            list_names_domains = [d.name() for d in list_all_domains]
            dict_domains = dict(zip(list_names_domains, list_all_domains))

            if action["id_domain"] in list_names_domains:
                domain = dict_domains[action["id_domain"]]
                self._handle_paused_domain_test(domain, action, action_time, intervals)
            else:
                self._handle_domain_not_found_in_pause(action, action_time, intervals)

        except libvirtError as e:
            self._handle_libvirt_error_in_start_paused(
                e, action, action_time, intervals
            )
        except Exception as e:
            self._handle_generic_error_in_start_paused(
                e, action, action_time, intervals
            )

    def _handle_paused_domain_test(self, domain, action, action_time, intervals):
        """Handle testing of paused domain"""
        domain_active = True
        try:
            # Test domain is active then destroy it
            lt = time.time()
            domain.isActive()
            intervals.append({"libvirt domain.isActive()": round(time.time() - lt, 3)})

            lt = time.time()
            domain.destroy()
            intervals.append({"libvirt domain.destroy()": round(time.time() - lt, 3)})

            try:
                lt = time.time()
                domain.isActive()
                intervals.append(
                    {"libvirt domain.isActive()": round(time.time() - lt, 3)}
                )
            except Exception:
                logs.exception_id.debug("0060")
                logs.workers.debug(
                    f"Verified domain {action['id_domain']} is destroyed"
                )

            update_last_hyp_id(action["id_domain"], last_hyp_id=self.hyp_id)
            domain_active = False
        except libvirtError as e:
            error_msg = pformat(e.get_error_message())
            update_domain_status(
                "Failed",
                action["id_domain"],
                hyp_id=self.hyp_id,
                detail=f"Domain failed when trying to destroy from paused state",
            )
            logs.workers.error(
                f"Exception in libvirt starting paused XML for domain {action['id_domain']} "
                f"in hypervisor {self.hyp_id}. Exception: {error_msg}"
            )
            log_action(
                self.hyp_id,
                action["id_domain"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Failed",
            )
            return

        # Handle test result
        if not domain_active:
            # Success case
            update_domain_status(
                "Stopped",
                action["id_domain"],
                hyp_id="",
                detail=f"Domain created and test OK: Started, paused and now stopped",
            )
            logs.workers.debug(
                f"Domain {action['id_domain']} creating operation finished. Ready to use."
            )
            log_action(
                self.hyp_id,
                action["id_domain"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Stopped",
            )
        else:
            # Failed to destroy properly
            update_domain_status(
                "Crashed",
                action["id_domain"],
                hyp_id=self.hyp_id,
                detail="Domain is created, started in pause mode but not destroyed",
            )
            log_action(
                self.hyp_id,
                action["id_domain"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Crashed",
            )

    def _handle_domain_not_found_in_pause(self, action, action_time, intervals):
        """Handle case where domain isn't found in paused domains list"""
        update_domain_status(
            "Crashed",
            action["id_domain"],
            hyp_id=self.hyp_id,
            detail=f"XML for domain cannot start in pause mode, unknown cause",
        )
        logs.workers.error(
            f"XML for domain {action['id_domain']} cannot start in pause mode in "
            f"hypervisor {self.hyp_id}, unknown cause"
        )
        log_action(
            self.hyp_id,
            action["id_domain"],
            action["type"],
            intervals,
            time.time() - action_time,
            "Crashed",
        )

    def _handle_libvirt_error_in_start_paused(self, e, action, action_time, intervals):
        """Handle libvirt errors in start_paused_domain"""
        error_msg = pformat(e.get_error_message())
        update_domain_status(
            "Failed",
            action["id_domain"],
            hyp_id=self.hyp_id,
            detail=f"Domain failed to start in pause mode",
        )
        logs.workers.error(
            f"Exception in libvirt starting paused XML for domain {action['id_domain']} "
            f"in hypervisor {self.hyp_id}. Exception: {error_msg}"
        )
        log_action(
            self.hyp_id,
            action["id_domain"],
            action["type"],
            intervals,
            time.time() - action_time,
            "Failed",
        )

    def _handle_generic_error_in_start_paused(self, e, action, action_time, intervals):
        """Handle generic errors in start_paused_domain"""
        logs.exception_id.debug("0061")
        update_domain_status(
            "Crashed",
            action["id_domain"],
            hyp_id=self.hyp_id,
            detail=f"Domain failed to start in pause mode: {e}",
        )
        logs.workers.error(
            f"Exception starting paused XML for domain {action['id_domain']}: {e}"
        )
        log_action(
            self.hyp_id,
            action["id_domain"],
            action["type"],
            intervals,
            time.time() - action_time,
            "Crashed",
        )

    def _is_old_ovs_hypervisor(self):
        """Check if this hypervisor uses old-style libvirt-managed OVS"""
        return get_table_field("hypervisors", self.hyp_id, "old_ovs") is True

    def _convert_xml_to_old_ovs(self, xml_str):
        """Convert new ethernet interfaces to old libvirt-managed OVS style

        Transforms:
          <interface type='ethernet'>
            <mac address='XX:XX:XX:XX:XX:XX'/>
            <model type='virtio'/>
            <driver name='vhost'/>
          </interface>

        To:
          <interface type='bridge'>
            <source bridge='ovsbr0'/>
            <mac address='XX:XX:XX:XX:XX:XX'/>
            <virtualport type='openvswitch'/>
            <vlan><tag id='VLAN_ID'/></vlan>
            <model type='virtio'/>
          </interface>

        Uses mac2network metadata to get VLAN IDs, then removes the metadata.
        """
        from io import StringIO

        from lxml import etree

        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(StringIO(xml_str), parser)
        root = tree.getroot()

        # Extract mac2network mappings from metadata
        isard_ns = "http://isardvdi.com"
        mac2vlan = {}
        mac2bridge = {}
        mac2network = root.find(f".//{{{isard_ns}}}mac2network")
        if mac2network is not None:
            for mapping in mac2network.findall(f"{{{isard_ns}}}mapping"):
                mac = mapping.get("mac", "").lower()
                vlan_id = mapping.get("vlan_id")
                bridge = mapping.get("bridge", "ovsbr0")
                if mac and vlan_id:
                    mac2vlan[mac] = vlan_id
                    mac2bridge[mac] = bridge
            # Remove mac2network metadata (old hypervisors don't need it)
            mac2network.getparent().remove(mac2network)

        # Convert ethernet interfaces to bridge+ovs
        for iface in root.findall(".//interface[@type='ethernet']"):
            mac_elem = iface.find("mac")
            if mac_elem is None:
                continue
            mac = mac_elem.get("address", "").lower()
            vlan_id = mac2vlan.get(mac)

            if vlan_id:
                # Change type to bridge
                iface.set("type", "bridge")

                # Add source bridge
                source = etree.SubElement(iface, "source")
                source.set("bridge", mac2bridge.get(mac, "ovsbr0"))

                # Add virtualport
                vport = etree.SubElement(iface, "virtualport")
                vport.set("type", "openvswitch")

                # Add VLAN tag
                vlan = etree.SubElement(iface, "vlan")
                tag = etree.SubElement(vlan, "tag")
                tag.set("id", str(vlan_id))

                # Remove driver element (not used in bridge type)
                driver = iface.find("driver")
                if driver is not None:
                    iface.remove(driver)
            else:
                logs.workers.warning(
                    f"No VLAN mapping found for MAC {mac} on old_ovs hypervisor {self.hyp_id}"
                )

        return etree.tostring(root, encoding="unicode", pretty_print=True)

    def _handle_start_domain(self, action, action_time, intervals):
        """Handle start_domain action"""
        xml = action["xml"]

        # Convert to old-style OVS XML for legacy hypervisors
        if self._is_old_ovs_hypervisor():
            xml = self._convert_xml_to_old_ovs(xml)
            logs.workers.debug(
                f"Converted XML to old-style OVS for hypervisor {self.hyp_id}"
            )

        logs.workers.debug(f"XML to start domain: {xml[30:100]}")

        try:
            # Create the domain
            lt = time.time()
            dom = self.h.conn.createXML(xml)
            intervals.append({"libvirt createXML": round(time.time() - lt, 3)})

            # Get XML description
            lt = time.time()
            xml_started = dom.XMLDesc()
            intervals.append({"libvirt XMLDesc": round(time.time() - lt, 3)})

            # Process domain startup
            self._process_domain_startup(xml_started, action, action_time, intervals)

        except libvirtError as e:
            self._handle_libvirt_error_in_start_domain(
                e, action, action_time, intervals
            )
        except Exception as e:
            self._handle_generic_error_in_start_domain(
                e, action, action_time, intervals
            )

    def _process_domain_startup(self, xml_started, action, action_time, intervals):
        """Process successful domain startup"""
        try:
            # Parse XML and get graphics ports
            xt = time.time()
            vm = DomainXML(xml_started, id_domain=action["id_domain"])
            intervals.append({"DomainXML": round(time.time() - xt, 3)})

            vt = time.time()
            spice, spice_tls, vnc, vnc_websocket = vm.get_graphics_port()
            intervals.append({"get_graphics_port": round(time.time() - vt, 3)})

            # Update domain viewer values
            dom_id = action["id_domain"]
            update_domain_viewer_started_values(
                dom_id,
                hyp_id=self.hyp_id,
                hyp_viewer=self.viewer.get("viewer", {}),
                hyp_tls=self.viewer.get("tls", {}),
                spice=spice,
                spice_tls=spice_tls,
                vnc=vnc,
                vnc_websocket=vnc_websocket,
                status="Started",
                detail="Domain started by worker",
            )

            # Update vGPU info if applicable
            if action.get("nvidia_uid", False) is not False:
                update_vgpu_uuid_domain_action(
                    action["vgpu_id"],
                    action["nvidia_uid"],
                    "domain_started",
                    domain_id=action["id_domain"],
                    profile=action["profile"],
                )

            # Log success
            logs.status.info(
                f"DOMAIN STARTED INFO WORKER - {dom_id} in {self.hyp_id} "
                f"(spice: {spice} / spicetls:{spice_tls} / vnc: {vnc} / "
                f"vnc_websocket: {vnc_websocket})"
            )
            logs.workers.info(
                f"STARTED domain {action['id_domain']} in hypervisor {self.hostname}"
            )
            log_action(
                self.hyp_id,
                action["id_domain"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Started",
            )

        except Exception as e:
            logs.exception_id.debug("0062")
            update_domain_status(
                "Failed",
                action["id_domain"],
                hyp_id=self.hyp_id,
                detail=f"Exception when starting domain: {e}",
            )
            logs.workers.error(f"Exception in start_domain action: {e}")

            if action.get("nvidia_uid", False) is not False:
                update_vgpu_uuid_domain_action(
                    action["vgpu_id"],
                    action["nvidia_uid"],
                    "domain_stopped",
                    domain_id=action["id_domain"],
                    profile=action["profile"],
                )
            log_action(
                self.hyp_id,
                action["id_domain"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Failed",
            )

    def _handle_libvirt_error_in_start_domain(self, e, action, action_time, intervals):
        """Handle libvirt errors in start_domain"""
        error_str = str(e)
        if "already exists with uuid" in error_str:
            logs.workers.error(
                f"Domain {action['id_domain']} already active! Fixed to Started in database"
            )
            update_domain_status(
                id_domain=action["id_domain"],
                status="Started",
                hyp_id=self.hyp_id,
                detail="Domain already active",
            )
            log_action(
                self.hyp_id,
                action["id_domain"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Started",
            )
        else:
            update_domain_status(
                "Failed",
                action["id_domain"],
                hyp_id=self.hyp_id,
                detail=f"Hypervisor cannot create domain: {error_str}",
            )
            logs.workers.error(f"Exception in start_domain action: {e}")
            log_action(
                self.hyp_id,
                action["id_domain"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Failed",
            )

            # Handle lost connection
            if "internal error: client socket is closed" in error_str:
                update_hyp_status(self.hyp_id, "Error", detail=error_str)
                self.stop = True
                self._cleanup_queued_actions()
                update_domains_started_in_hyp_to_unknown(self.hyp_id)

    def _handle_generic_error_in_start_domain(self, e, action, action_time, intervals):
        """Handle generic errors in start_domain"""
        logs.exception_id.debug("0062")
        update_domain_status(
            "Failed",
            action["id_domain"],
            hyp_id=self.hyp_id,
            detail=f"Exception when starting domain: {e}",
        )
        logs.workers.error(f"Exception in start_domain action: {e}")

        if action.get("nvidia_uid", False) is not False:
            update_vgpu_uuid_domain_action(
                action["vgpu_id"],
                action["nvidia_uid"],
                "domain_stopped",
                domain_id=action["id_domain"],
                profile=action["profile"],
            )
        log_action(
            self.hyp_id,
            action["id_domain"],
            action["type"],
            intervals,
            time.time() - action_time,
            "Failed",
        )

    def _handle_shutdown_domain(self, action, action_time, intervals):
        """Handle shutdown_domain action"""
        logs.workers.debug(f"Action shutdown domain: {action['id_domain']}")

        domain, error = self._lookup_domain(action, intervals, "shutdown")
        if error:
            # Handle case where domain is already gone (stopped by another operation)
            if (
                isinstance(error, libvirtError)
                and error.get_error_code() == VIR_ERR_NO_DOMAIN
            ):
                logs.workers.info(
                    f"Domain {action['id_domain']} not found during shutdown - already stopped"
                )
                # Don't set to Failed - domain is already in desired end state
                return

            self._handle_domain_action_error(
                action, error, action_time, intervals, "shutdown"
            )
            return

        try:
            # Send ACPI shutdown signal
            lt = time.time()
            domain.shutdownFlags(VIR_DOMAIN_SHUTDOWN_ACPI_POWER_BTN)
            intervals.append({"domain.shutdownFlags": round(time.time() - lt, 3)})

            # Update status and log
            logs.workers.debug(f"SHUTTING-DOWN domain {action['id_domain']}")
            update_domain_status(
                "Shutting-down",
                action["id_domain"],
                hyp_id=self.hyp_id,
                detail="shutdown ACPI_POWER_BTN launched in libvirt domain",
            )
            log_action(
                self.hyp_id,
                action["id_domain"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Shutting-down",
            )
        except libvirtError as e:
            # Handle case where domain disappeared between lookup and shutdown
            if e.get_error_code() == VIR_ERR_NO_DOMAIN:
                logs.workers.info(
                    f"Domain {action['id_domain']} disappeared during shutdown - already stopped"
                )
                return
            else:
                self._handle_domain_action_error(
                    action, e, action_time, intervals, "shutdown"
                )
        except Exception as e:
            self._handle_domain_action_error(
                action, e, action_time, intervals, "shutdown"
            )

    def _handle_stop_domain(self, action, action_time, intervals):
        """Handle stop_domain action"""
        logs.workers.debug(f"Action stop domain: {action['id_domain']}")

        domain, error = self._lookup_domain(action, intervals, "stop")
        if error:

            ## Hande libvirtNotfound

            if (
                isinstance(error, libvirtError)
                and error.get_error_code() == VIR_ERR_NO_DOMAIN
            ):
                # Domain already undefined, which is OK
                self._finalize_domain_stop(action, action_time, intervals)
                return

            self._handle_domain_action_error(
                action, error, action_time, intervals, "stop"
            )
            return

        try:
            # Destroy the domain
            lt = time.time()
            domain.destroy()
            intervals.append({"domain.destroy": round(time.time() - lt, 3)})

            # Finalize the stop operation
            self._finalize_domain_stop(action, action_time, intervals)

        except libvirtError as e:
            # Check if domain not found during destroy - this is OK for stop operation
            if e.get_error_code() == VIR_ERR_NO_DOMAIN:
                logs.workers.info(
                    f"Domain {action['id_domain']} not found during destroy - already stopped"
                )
                self._finalize_domain_stop(action, action_time, intervals)
            else:
                self._handle_domain_action_error(
                    action, e, action_time, intervals, "stop"
                )
        except Exception as e:
            self._handle_domain_action_error(action, e, action_time, intervals, "stop")

    def _finalize_domain_stop(self, action, action_time, intervals):
        """Finalize domain stop operation"""
        logs.workers.info(f"DESTROY OK domain {action['id_domain']}")

        try:
            # Handle post-stop actions
            check_if_delete = action.get("delete_after_stopped", False)
            if action.get("not_change_status", False) is False:
                if check_if_delete:
                    update_domain_status("Stopped", action["id_domain"], hyp_id="")
                    update_vgpu_info_if_stopped(action["id_domain"])
                    update_domain_status("Deleting", action["id_domain"], hyp_id="")
                    log_action(
                        self.hyp_id,
                        action["id_domain"],
                        action["type"],
                        intervals,
                        time.time() - action_time,
                        "Stopped and Deleting",
                    )
                else:
                    update_domain_status("Stopped", action["id_domain"], hyp_id="")
                    update_vgpu_info_if_stopped(action["id_domain"])
                    log_action(
                        self.hyp_id,
                        action["id_domain"],
                        action["type"],
                        intervals,
                        time.time() - action_time,
                        "Stopped",
                    )
        except Exception as e:
            logs.exception_id.debug("0065")
            if action.get("not_change_status", False) is False:
                update_domain_status(
                    "Failed",
                    action["id_domain"],
                    hyp_id=self.hyp_id,
                    detail=str(e),
                )
            log_action(
                self.hyp_id,
                action["id_domain"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Failed",
            )

    def _handle_reset_domain(self, action, action_time, intervals):
        """Handle reset_domain action"""
        logs.workers.debug(f"Action reset domain: {action['id_domain']}")

        domain, error = self._lookup_domain(action, intervals, "reset")
        if error:
            self._handle_domain_action_error(
                action, error, action_time, intervals, "reset"
            )
            return

        try:
            # Reset the domain
            lt = time.time()
            domain.reset()
            intervals.append({"domain.reset": round(time.time() - lt, 3)})

            # Update status and log
            update_domain_status(
                id_domain=action["id_domain"],
                status="Started",
                hyp_id=self.hyp_id,
                detail="Desktop resetted",
            )
            logs.workers.info(f"RESET OK domain {action['id_domain']}")
            log_action(
                self.hyp_id,
                action["id_domain"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Started",
            )
        except Exception as e:
            self._handle_domain_action_error(action, e, action_time, intervals, "reset")

    def _handle_domain_action_error(
        self, action, error, action_time, intervals, operation
    ):
        """Handle errors in domain actions"""
        log_id = {"shutdown": "0063", "stop": "0065", "reset": "0068"}.get(
            operation, "0000"
        )
        logs.exception_id.debug(log_id)

        if action.get("not_change_status", False) is False:
            update_domain_status(
                "Failed",
                action["id_domain"],
                hyp_id=self.hyp_id,
                detail=str(error),
            )

        logs.workers.error(
            f"Exception in {operation} domain {action['id_domain']}: {error}"
        )
        log_action(
            self.hyp_id,
            action["id_domain"],
            action["type"],
            intervals,
            time.time() - action_time,
            "Failed",
        )

    def _handle_disk_action(self, action, action_time, intervals, operation_type):
        """Handle disk actions (create or delete)"""
        t = time.time()
        try:
            # Launch disk action
            launch_action_disk(
                action, self.hostname, user=self.h.user, port=self.h.port
            )
            intervals.append({f"{operation_type}_disk": round(time.time() - t, 3)})

            # Log result
            log_action(
                self.hyp_id,
                action.get("domain"),
                action["type"],
                intervals,
                time.time() - action_time,
                "Finished",
            )
        except Exception as e:
            logs.workers.error(f"Error in {action['type']} action: {e}")
            log_action(
                self.hyp_id,
                action.get("domain"),
                action["type"],
                intervals,
                time.time() - action_time,
                "Failed",
            )

    def _handle_killall_curl(self, action, action_time, intervals):
        """Handle killall_curl action"""
        t = time.time()
        try:
            launch_killall_curl(self.hostname, user=self.h.user, port=self.h.port)
            intervals.append({"killall_curl": round(time.time() - t, 3)})

            log_action(
                self.hyp_id,
                None,
                action["type"],
                intervals,
                time.time() - action_time,
                "Finished",
            )
        except Exception as e:
            logs.workers.error(f"Error in killall_curl action: {e}")
            log_action(
                self.hyp_id,
                None,
                action["type"],
                intervals,
                time.time() - action_time,
                "Failed",
            )

    def _handle_delete_media(self, action, action_time, intervals):
        """Handle delete_media action"""
        final_status = action.get("final_status", "Deleted")
        t = time.time()

        try:
            launch_delete_media(
                action,
                self.hostname,
                user=self.h.user,
                port=self.h.port,
                final_status=final_status,
            )
            intervals.append({"delete_media": round(time.time() - t, 3)})

            log_action(
                self.hyp_id,
                None,
                action["type"],
                intervals,
                time.time() - action_time,
                final_status,
            )
        except Exception as e:
            logs.workers.error(f"Error in delete_media action: {e}")
            log_action(
                self.hyp_id,
                None,
                action["type"],
                intervals,
                time.time() - action_time,
                "Failed",
            )

    def _handle_update_status(self, action, action_time, intervals):
        """Handle update_status_db_from_running_domains action"""
        t = time.time()
        try:
            update_status_db_from_running_domains(self.h)
            intervals.append({"update_status": round(time.time() - t, 3)})

            log_action(
                self.hyp_id,
                None,
                action["type"],
                intervals,
                time.time() - action_time,
                "Finished",
            )
        except Exception as e:
            logs.workers.error(f"Error updating status: {e}")
            log_action(
                self.hyp_id,
                None,
                action["type"],
                intervals,
                time.time() - action_time,
                "Failed",
            )

    def _handle_hyp_info(self, action, action_time, intervals):
        """Handle hyp_info action"""
        try:
            t = time.time()
            self.h.get_kvm_mod()
            intervals.append({"get_kvm_mod": round(time.time() - t, 3)})

            t = time.time()
            self.h.get_hyp_info()
            intervals.append({"get_hyp_info": round(time.time() - t, 3)})

            logs.workers.debug(
                f"Hypervisor motherboard: {self.h.info.get('motherboard_manufacturer', 'unknown')}"
            )
            update_db_hyp_info(self.hyp_id, self.h.info)

            log_action(
                self.hyp_id,
                None,
                action["type"],
                intervals,
                time.time() - action_time,
                "Finished",
            )
        except Exception as e:
            logs.workers.error(f"Error getting hypervisor info: {e}")
            log_action(
                self.hyp_id,
                None,
                action["type"],
                intervals,
                time.time() - action_time,
                "Failed",
            )

    def _handle_notify(self, action, action_time, intervals):
        """Handle notify action"""
        try:
            t = time.time()
            domain = self.h.conn.lookupByName(action["desktop_id"])
            intervals.append({"conn.lookupByName": round(time.time() - t, 3)})

            notify_thread_pool.submit(
                notify_desktop_in_thread, domain, action["message"]
            )

            log_action(
                self.hyp_id,
                action["desktop_id"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Finished",
            )
        except libvirtError as error:
            logs.workers.error(
                f"Libvirt error getting desktop {action['desktop_id']} to notify: {error}"
            )
            log_action(
                self.hyp_id,
                action["desktop_id"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Failed",
            )
        except Exception as error:
            logs.workers.error(f"Error in notify action: {error}")

    def _handle_personal_unit(self, action, action_time, intervals):
        """Handle personal_unit action"""
        if not NOTIFY_PERSONAL_UNIT:
            return

        try:
            t = time.time()
            domain = self.h.conn.lookupByName(action["desktop_id"])
            intervals.append({"conn.lookupByName": round(time.time() - t, 3)})

            personal_unit_thread_pool.submit(personal_unit_in_thread, domain)

            log_action(
                self.hyp_id,
                action["desktop_id"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Finished",
            )
        except libvirtError as error:
            logs.workers.error(
                f"Libvirt error getting desktop {action['desktop_id']} for personal unit: {error}"
            )
            log_action(
                self.hyp_id,
                action["desktop_id"],
                action["type"],
                intervals,
                time.time() - action_time,
                "Failed",
            )
        except Exception as error:
            logs.workers.error(f"Error in personal_unit action: {error}")

    def _cleanup_queued_actions(self):
        """Clean up queued actions for this hypervisor when connection is lost"""
        for action in list(self.queue_actions.queue):
            try:
                if (
                    isinstance(action, tuple)
                    and len(action) >= 3
                    and isinstance(action[2], dict)
                ):
                    queue_item = action[2]
                    if queue_item.get("hyp_id") == self.hyp_id:
                        if queue_item.get("type") == "start_domain":
                            update_domain_status(
                                "Stopped",
                                queue_item["id_domain"],
                                hyp_id=self.hyp_id,
                                detail="Domain stopped due to hypervisor error",
                            )
                        else:
                            update_domain_status(
                                "Failed",
                                queue_item["id_domain"],
                                hyp_id=self.hyp_id,
                                detail="Domain failed due to hypervisor error",
                            )
                        self.queue_actions.queue.remove(action)
            except Exception as e:
                logs.workers.warning(f"Error cleaning up queue item: {e}")

    def get_positioned_items(self):
        """Get positioned items from the queue for display"""
        try:
            items = list(self.queue_actions.queue)

            # Filter items with required fields
            valid_items = [
                item
                for item in items
                if len(item) >= 3
                and isinstance(item[2], dict)
                and "id_domain" in item[2]
                and "type" in item[2]
            ]

            # Sort by priority and order
            sorted_items = sorted(valid_items, key=lambda item: (item[0], item[1]))

            # Create the result list
            positioned_items = [
                {
                    "priority": item[0],
                    "event": item[2]["type"],
                    "desktop_id": item[2]["id_domain"],
                    "position": idx + 1,
                }
                for idx, item in enumerate(sorted_items)
                if item[2]["type"] in ITEMS_STATUS_MAP
            ]

            return positioned_items
        except Exception as e:
            logs.workers.error(f"Error getting positioned items: {e}")
            return []

    def update_desktops_queue(self):
        """Update the desktops queue via the API"""
        current_time = time.time()
        # Only update every 10 seconds
        if current_time - self.last_api_call_time <= 10:
            return

        self.last_api_call_time = current_time
        positioned_items = self.get_positioned_items()

        # Only send if there are items
        if positioned_items:
            try:
                api_client.put(
                    f"/notify/desktops/queue/{self.hyp_id}",
                    data=positioned_items,
                    timeout=0.0000000001,  # Very small timeout as in original code
                )
            except requests_ReadTimeout:
                # Expected due to very small timeout
                pass
            except Exception as e:
                logs.workers.error(f"Error updating desktops queue: {e}")
