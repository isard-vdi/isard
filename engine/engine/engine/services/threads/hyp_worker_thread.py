# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import base64
import queue
import threading
import time

from engine.models.domain_xml import DomainXML
from engine.models.hyp import hyp
from engine.services.db import (
    get_hyp_hostname_from_id,
    get_hyp_status,
    get_hyp_viewer_info,
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

    def run(self):
        self.tid = get_tid()
        logs.workers.info("starting thread: {} (TID {})".format(self.name, self.tid))
        (
            host,
            port,
            user,
            nvidia_enabled,
            force_get_hyp_info,
            init_vgpu_profiles,
        ) = get_hyp_hostname_from_id(self.hyp_id)
        if host is False:
            self.stop = True
            self.error = "hostname not in database"
        else:
            port = int(port)
            self.hostname = host
            try:
                self.h = hyp(
                    self.hyp_id,
                    self.hostname,
                    user=user,
                    port=port,
                    nvidia_enabled=nvidia_enabled,
                )
                if not self.h.conn:
                    self.error = "cannot connect to libvirt"
                    update_hyp_status(self.hyp_id, "Error", detail=self.error)
                    self.stop = True
                elif self.h.conn.isAlive() == 1:
                    # TRY IF SSH COMMAND RUN:
                    cmds = [{"cmd": "uname -a"}]
                    try:
                        array_out_err = exec_remote_list_of_cmds_dict(
                            host, cmds, username=user, port=port
                        )
                        output = array_out_err[0]["out"]
                        logs.main.debug(f"cmd: {cmds[0]}, output: {output}")
                        if len(output) > 0:
                            # TEST OK
                            launch_killall_curl(self.hostname, user, port)
                            # UPDATE DOMAIN STATUS
                            self.h.update_domain_coherence_in_db()

                            update_hyp_thread_status("worker", self.hyp_id, "Started")
                            self.q_event_register.put(
                                {
                                    "type": "add_hyp_to_receive_events",
                                    "hyp_id": self.hyp_id,
                                    "worker": self,
                                }
                            )

                        else:
                            self.error = "output from command uname -a is empty, ssh action failed"
                            update_hyp_status(self.hyp_id, "Error", detail=self.error)
                            self.stop = True
                    except Exception as e:
                        logs.exception_id.debug("0058")
                        self.error = "testing ssh connection failed. Exception: {e}"
                        update_hyp_status(self.hyp_id, "Error", detail=self.error)
                        self.stop = True
                else:
                    self.error = "libvirt not alive"
                    update_hyp_status(self.hyp_id, "Error", detail=self.error)
                    self.stop = True
            except Exception as e:
                logs.exception_id.debug("0059")
                self.error = f"Exception: {e}"
                update_hyp_status(self.hyp_id, "Error", detail=self.error)
                self.stop = True

            try:
                hyp_id = self.hyp_id
                if self.stop is not True:
                    # get info from hypervisor
                    self.h.get_info_from_hypervisor(
                        nvidia_enabled=nvidia_enabled,
                        force_get_hyp_info=force_get_hyp_info,
                        # force_get_hyp_info=True,
                        init_vgpu_profiles=init_vgpu_profiles,
                    )

                    update_table_field(
                        "hypervisors",
                        self.hyp_id,
                        "viewer_status",
                        self.h.get_hyp_video_status(),
                        soft=True,
                    )

                    self.h.get_system_stats()

                    # load info and nvidia info from db
                    self.h.load_info_from_db()

                    # INIT

                    if nvidia_enabled:
                        self.h.init_nvidia()
                        logs.workers.debug(
                            f"nvidia info updated in hypervisor {self.hyp_id}"
                        )

                    if (
                        self.h.info["kvm_module"] == "intel"
                        or self.h.info["kvm_module"] == "amd"
                    ):
                        self.stop = False
                    else:
                        logs.workers.error(
                            "hypervisor {} has not virtualization support (VT-x for Intel processors and AMD-V for AMD processors). ".format(
                                hyp_id
                            )
                        )
                        update_hyp_status(
                            hyp_id,
                            "Error",
                            detail="KVM requires that the virtual machine host's processor has virtualization "
                            + "support (named VT-x for Intel processors and AMD-V for AMD processors). "
                            + "Check CPU capabilities and enable virtualization support in your BIOS.",
                        )
                        self.stop = True
            except Exception as e:
                logs.exception_id.debug("0059")
                self.error = f"Hypervisor {hyp_id} failed to get info. Exception: {e}"
                update_hyp_status(self.hyp_id, "Error", detail=self.error)
                self.stop = True
        if self.stop is not True:
            update_table_field(
                "hypervisors", self.hyp_id, "stats", self.h.stats, soft=True
            )
            update_hyp_status(self.hyp_id, "Online")

        update_stats = time.time()
        self.current_action = {}
        while self.stop is not True:
            try:
                # do={type:'start_domain','xml':'xml','id_domain'='prova'}
                action = self.queue_actions.get(timeout=TIMEOUT_QUEUES)
                self.current_action = action
                if action["type"] == "start_paused_domain":
                    logs.workers.debug(
                        "xml to start paused some lines...: {}".format(
                            action["xml"][30:100]
                        )
                    )
                    try:
                        self.h.conn.createXML(
                            action["xml"], flags=VIR_DOMAIN_START_PAUSED
                        )
                        # nvidia_uid = action.get("nvidia_uid", False)
                        # if nvidia_uid is not False:
                        #     ok = update_info_nvidia_hyp_domain(
                        #         "started", nvidia_uid, hyp_id, action["id_domain"]
                        #     )
                        # 32 is the constant for domains paused
                        # reference: https://libvirt.org/html/libvirt-libvirt-domain.html#VIR_CONNECT_LIST_DOMAINS_PAUSED

                        FLAG_LIST_DOMAINS_PAUSED = 32
                        list_all_domains = self.h.conn.listAllDomains(
                            FLAG_LIST_DOMAINS_PAUSED
                        )
                        list_names_domains = [d.name() for d in list_all_domains]
                        dict_domains = dict(zip(list_names_domains, list_all_domains))
                        if action["id_domain"] in list_names_domains:
                            # domain started in pause mode
                            domain = dict_domains[action["id_domain"]]
                            domain_active = True
                            try:
                                domain.isActive()
                                domain.destroy()
                                try:
                                    domain.isActive()
                                except Exception as e:
                                    logs.exception_id.debug("0060")
                                    logs.workers.debug(
                                        "verified domain {} is destroyed".format(
                                            action["id_domain"]
                                        )
                                    )
                                update_last_hyp_id(
                                    action["id_domain"], last_hyp_id=hyp_id
                                )

                                domain_active = False

                            except libvirtError as e:
                                from pprint import pformat

                                error_msg = pformat(e.get_error_message())

                                update_domain_status(
                                    "Failed",
                                    action["id_domain"],
                                    hyp_id=self.hyp_id,
                                    detail="domain {} failed when try to destroy from paused domain in hypervisor {}. creating domain operation is aborted",
                                )
                                logs.workers.error(
                                    "Exception in libvirt starting paused xml for domain {} in hypervisor {}. Exception message: {} ".format(
                                        action["id_domain"], self.hyp_id, error_msg
                                    )
                                )
                                continue

                            if domain_active is False:
                                # domain is destroyed, all ok
                                update_domain_status(
                                    "Stopped",
                                    action["id_domain"],
                                    hyp_id="",
                                    detail="Domain created and test OK: Started, paused and now stopped in hyp {}".format(
                                        self.hyp_id
                                    ),
                                )

                                logs.workers.debug(
                                    "domain {} creating operation finalished. Started paused and destroyed in hypervisor {}. Now status is Stopped. READY TO USE".format(
                                        action["id_domain"], self.hyp_id
                                    )
                                )

                            else:
                                update_domain_status(
                                    "Crashed",
                                    action["id_domain"],
                                    hyp_id=self.hyp_id,
                                    detail="Domain is created, started in pause mode but not destroyed,creating domain operation is aborted",
                                )
                                logs.workers.error(
                                    "domain {} started paused but not destroyed in hypervisor {}, must be destroyed".format(
                                        action["id_domain"], self.hyp_id
                                    )
                                )
                        else:
                            update_domain_status(
                                "Crashed",
                                action["id_domain"],
                                hyp_id=self.hyp_id,
                                detail="XML for domain {} can not start in pause mode in hypervisor {}, creating domain operation is aborted by unknown cause".format(
                                    action["id_domain"], self.hyp_id
                                ),
                            )
                            logs.workers.error(
                                "XML for domain {} can not start in pause mode in hypervisor {}, creating domain operation is aborted, not exception, rare case, unknown cause".format(
                                    action["id_domain"], self.hyp_id
                                )
                            )

                    except libvirtError as e:
                        from pprint import pformat

                        error_msg = pformat(e.get_error_message())

                        update_domain_status(
                            "Failed",
                            action["id_domain"],
                            hyp_id=self.hyp_id,
                            detail="domain {} failed when try to start in pause mode in hypervisor {}. creating domain operation is aborted",
                        )
                        logs.workers.error(
                            "Exception in libvirt starting paused xml for domain {} in hypervisor {}. Exception message: {} ".format(
                                action["id_domain"], self.hyp_id, error_msg
                            )
                        )
                    except Exception as e:
                        logs.exception_id.debug("0061")
                        update_domain_status(
                            "Crashed",
                            action["id_domain"],
                            hyp_id=self.hyp_id,
                            detail="domain {} failed when try to start in pause mode in hypervisor {}. creating domain operation is aborted",
                        )
                        logs.workers.error(
                            "Exception starting paused xml for domain {} in hypervisor {}. NOT LIBVIRT EXCEPTION, RARE CASE. Exception message: {}".format(
                                action["id_domain"], self.hyp_id, str(e)
                            )
                        )

                ## START DOMAIN
                elif action["type"] == "start_domain":
                    logs.workers.debug(
                        "xml to start some lines...: {}".format(action["xml"][30:100])
                    )
                    try:
                        dom = self.h.conn.createXML(action["xml"])
                    except libvirtError as e:
                        if "already exists with uuid" in str(e):
                            logs.workers.error(
                                "Domain {} set to Starting status, but when worker want to start it, it is already active!! Fixed to Started in database".format(
                                    action["id_domain"]
                                )
                            )
                            update_domain_status(
                                id_domain=action["id_domain"],
                                status="Started",
                                hyp_id=hyp_id,
                                detail="Ups, domain already active",
                            )
                        else:
                            update_domain_status(
                                "Failed",
                                action["id_domain"],
                                hyp_id=self.hyp_id,
                                detail=(
                                    "Hypervisor can not create domain with libvirt exception: "
                                    + str(e)
                                ),
                            )
                            logs.workers.info(
                                "exception 01 in start_domain action {}: ".format(e)
                            )
                    else:
                        try:
                            xml_started = dom.XMLDesc()
                        except libvirtError as e:
                            update_domain_status(
                                "Failed",
                                action["id_domain"],
                                hyp_id=self.hyp_id,
                                detail=(
                                    "Hypervisor can not create domain with libvirt exception: "
                                    + str(e)
                                ),
                            )
                            logs.workers.info(
                                "exception 02 in start_domain action {}: ".format(e)
                            )
                        else:
                            try:
                                vm = DomainXML(
                                    xml_started, id_domain=action["id_domain"]
                                )
                                (
                                    spice,
                                    spice_tls,
                                    vnc,
                                    vnc_websocket,
                                ) = vm.get_graphics_port()
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

                                if action.get("nvidia_uid", False) is not False:
                                    update_vgpu_uuid_domain_action(
                                        action["vgpu_id"],
                                        action["nvidia_uid"],
                                        "domain_started",
                                        domain_id=action["id_domain"],
                                        profile=action["profile"],
                                    )
                                logs.status.info(
                                    f"DOMAIN STARTED INFO WORKER - {dom_id} in {self.hyp_id} (spice: {spice} / spicetls:{spice_tls} / vnc: {vnc} / vnc_websocket: {vnc_websocket})"
                                )
                                # wait to event started to save state in database
                                # update_domain_status('Started', action['id_domain'], hyp_id=self.hyp_id, detail='Domain has started in worker thread')
                                logs.workers.info(
                                    "STARTED domain {}: createdXML action in hypervisor {} has been sent".format(
                                        action["id_domain"], host
                                    )
                                )

                            except Exception as e:
                                logs.exception_id.debug("0062")
                                update_domain_status(
                                    "Failed",
                                    action["id_domain"],
                                    hyp_id=self.hyp_id,
                                    detail=(
                                        "Exception when starting domain: " + str(e)
                                    ),
                                )
                                logs.workers.debug(
                                    "exception 03 in start_domain action {}: ".format(e)
                                )

                                if action.get("nvidia_uid", False) is not False:
                                    update_vgpu_uuid_domain_action(
                                        action["vgpu_id"],
                                        action["nvidia_uid"],
                                        "domain_stopped",
                                        domain_id=action["id_domain"],
                                        profile=action["profile"],
                                    )

                ## STOP DOMAIN
                elif action["type"] == "shutdown_domain":
                    logs.workers.debug(
                        "action shutdown domain: {}".format(action["id_domain"][30:100])
                    )
                    try:
                        domain_handler = self.h.conn.lookupByName(action["id_domain"])
                        # this function not shutdown via ACPI: domain_handler.shutdown()
                        # the flag that we use is: VIR_DOMAIN_SHUTDOWN_ACPI_POWER_BTN
                        # if we have agent we can use the constant: VIR_DOMAIN_SHUTDOWN_GUEST_AGENT
                        # using shutdownFlags you can control the behaviour of shutdown like virsh shutdown domain --mode MODE-LIST
                        domain_handler.shutdownFlags(VIR_DOMAIN_SHUTDOWN_ACPI_POWER_BTN)
                        logs.workers.debug(
                            "SHUTTING-DOWN domain {}".format(action["id_domain"])
                        )
                        update_domain_status(
                            "Shutting-down",
                            action["id_domain"],
                            hyp_id=hyp_id,
                            detail="shutdown ACPI_POWER_BTN launched in libvirt domain",
                        )
                    except Exception as e:
                        logs.exception_id.debug("0063")
                        logs.workers.error(
                            "Exception in domain {} when shutdown action in hypervisor {}".format(
                                action["id_domain"], hyp_id
                            )
                        )
                        logs.workers.error(f"Exception: {e}")

                ## STOP DOMAIN
                elif action["type"] == "stop_domain":
                    logs.workers.debug(
                        "action stop domain: {}".format(action["id_domain"][30:100])
                    )
                    try:
                        domain_handler = self.h.conn.lookupByName(action["id_domain"])
                        domain_handler.destroy()
                    except libvirtError as e:
                        if e.get_error_code() == VIR_ERR_NO_DOMAIN:
                            # already undefined
                            pass
                        else:
                            logs.exception_id.debug(
                                "0065: Libvirt error code: {}".format(
                                    e.get_error_code()
                                )
                            )
                            if action.get("not_change_status", False) is False:
                                update_domain_status(
                                    "Failed",
                                    action["id_domain"],
                                    hyp_id=self.hyp_id,
                                    detail=str(e),
                                )
                            logs.workers.info(
                                "exception in stopping domain {}: ".format(
                                    e.get_error_code()
                                )
                            )
                            continue
                    try:
                        # nvidia info updated in events_recolector

                        logs.workers.info(
                            "DESTROY OK domain {}".format(action["id_domain"])
                        )

                        check_if_delete = action.get("delete_after_stopped", False)
                        if action.get("not_change_status", False) is False:
                            if check_if_delete is True:
                                update_domain_status(
                                    "Stopped", action["id_domain"], hyp_id=""
                                )
                                update_vgpu_info_if_stopped(action["id_domain"])
                                update_domain_status(
                                    "Deleting", action["id_domain"], hyp_id=""
                                )
                            else:
                                update_domain_status(
                                    "Stopped", action["id_domain"], hyp_id=""
                                )
                                update_vgpu_info_if_stopped(action["id_domain"])

                    except Exception as e:
                        logs.exception_id.debug("0065")
                        if action.get("not_change_status", False) is False:
                            update_domain_status(
                                "Failed",
                                action["id_domain"],
                                hyp_id=self.hyp_id,
                                detail=str(e),
                            )
                        logs.workers.info("exception in stopping domain {}: ".format(e))

                ## RESET DOMAIN
                elif action["type"] == "reset_domain":
                    logs.workers.debug(
                        "action reset domain: {}".format(action["id_domain"][30:100])
                    )
                    try:
                        domain_handler = self.h.conn.lookupByName(action["id_domain"])
                        domain_handler.reset()
                        update_domain_status(
                            id_domain=action["id_domain"],
                            status="Started",
                            hyp_id=self.hyp_id,
                            detail="Desktop resetted",
                        )
                        logs.workers.info(
                            "RESET OK domain {}".format(action["id_domain"])
                        )

                    except Exception as e:
                        logs.exception_id.debug("0068")
                        update_domain_status(
                            "Failed",
                            action["id_domain"],
                            hyp_id=self.hyp_id,
                            detail=str(e),
                        )
                        logs.workers.info(
                            "exception in resetting domain {}: ".format(e)
                        )

                elif action["type"] in ["create_disk", "delete_disk"]:
                    launch_action_disk(action, self.hostname, user, port)

                elif action["type"] in ["add_media_hot"]:
                    pass

                elif action["type"] in ["killall_curl"]:
                    launch_killall_curl(self.hostname, user, port)

                elif action["type"] in ["delete_media"]:
                    final_status = action.get("final_status", "Deleted")

                    launch_delete_media(
                        action, self.hostname, user, port, final_status=final_status
                    )

                elif action["type"] == "create_disk":
                    pass

                elif action["type"] == "update_status_db_from_running_domains":
                    update_status_db_from_running_domains(self.h)

                elif action["type"] == "hyp_info":
                    self.h.get_kvm_mod()
                    self.h.get_hyp_info()
                    logs.workers.debug(
                        "hypervisor motherboard: {}".format(
                            self.h.info["motherboard_manufacturer"]
                        )
                    )
                    update_db_hyp_info(self.hyp_id, self.h.info)

                ## DESTROY THREAD
                elif action["type"] == "stop_thread":
                    self.stop = True

                elif action["type"] == "notify":
                    try:
                        domain = self.h.conn.lookupByName(action["desktop_id"])
                    except libvirtError as error:
                        logs.workers.error(
                            f'libvirt error getting desktop {action["desktop_id"]} to '
                            f'notify with "{base64.b64decode(action["message"])}": '
                            f"{error}"
                        )
                    else:
                        try:
                            Notifier.notify_desktop(domain, action["message"])

                        except Exception as error:
                            logs.workers.error(
                                f'error notifying desktop {action["desktop_id"]}: '
                                f'notify with "{base64.b64decode(action["message"])}": '
                                f"{error}"
                            )

                elif action["type"] == "personal_unit":
                    try:
                        domain = self.h.conn.lookupByName(action["desktop_id"])
                    except libvirtError as error:
                        logs.workers.error(
                            f'libvirt error getting desktop {action["desktop_id"]} to '
                            "mount personal unit: "
                            f"{error}"
                        )
                    else:
                        try:
                            PersonalUnit.connect_personal_unit(domain)

                        except Exception as error:
                            logs.workers.error(
                                f'error connecting the personal unit for desktop {action["desktop_id"]}'
                                f"{error}"
                            )

                else:
                    logs.workers.error(
                        "type action {} not supported in queue actions".format(
                            action["type"]
                        )
                    )
                    # time.sleep(0.1)
                    ## TRY DOMAIN

                try:
                    self.update_desktops_queue(self.get_queue_items())
                except Exception as e:
                    logs.workers.error(f"Error sending desktops queue to api: {e}")
            except queue.Empty:
                try:
                    self.h.conn.isAlive()
                    self.h.conn.getLibVersion()
                except:
                    logs.workers.info(
                        "trying to reconnect hypervisor {}, alive test in working thread failed".format(
                            host
                        )
                    )
                    alive = False
                    for i in range(RETRIES_HYP_IS_ALIVE):
                        logs.workers.info(
                            f"retry hyp connection {i}/{RETRIES_HYP_IS_ALIVE}"
                        )
                        try:
                            time.sleep(TIMEOUT_BETWEEN_RETRIES_HYP_IS_ALIVE)
                            self.h.conn.getLibVersion()
                            alive = True
                            logs.workers.info("hypervisor {} is alive".format(host))
                            break
                        except Exception as e:
                            logs.exception_id.debug("0066")
                            logs.workers.info(
                                "hypervisor {} is NOT alive. Exception: {}".format(
                                    host, e
                                )
                            )
                    if alive is False:
                        try:
                            self.h.connect_to_hyp()
                            self.h.conn.getLibVersion()
                            # UPDATE DOMAIN STATUS
                            self.h.update_domain_coherence_in_db()
                            update_hyp_status(self.hyp_id, "Online")
                        except:
                            logs.workers.debug("hypervisor {} failed".format(host))
                            logs.workers.error(
                                "fail reconnecting to hypervisor {} in working thread".format(
                                    host
                                )
                            )
                            reason = self.h.fail_connected_reason
                            status = get_hyp_status(self.hyp_id)
                            if status in ["Online"]:
                                update_hyp_status(self.hyp_id, "Error", reason)
                            update_domains_started_in_hyp_to_unknown(self.hyp_id)

                            # list_works_in_queue = list(self.queue_actions.queue)
                            logs.workers.error(
                                "thread worker from hypervisor {} exit from error status".format(
                                    hyp_id
                                )
                            )
                            self.error = True
                            self.stop = True
                            break

            self.current_action = {}
            if update_stats + 5 < time.time():
                self.h.get_system_stats()
                update_table_field(
                    "hypervisors", self.hyp_id, "stats", self.h.stats, soft=True
                )
                update_stats = time.time()
                logs.workers.debug(
                    "hypervisor {} stats updated in working thread".format(self.hyp_id)
                )
        try:
            update_hyp_thread_status("worker", self.hyp_id, "Stopping")
            try:
                self.h.disconnect()
            except Exception as e:
                logs.exception_id.debug("0066")
                logs.workers.error(
                    "Unable to disconnect from hypervisor {} in working thread: {}\n Have disappeared?".format(
                        self.hyp_id, e
                    )
                )
            self.q_event_register.put(
                {"type": "del_hyp_to_receive_events", "hyp_id": self.hyp_id}
            )
            action = {}
            action["type"] = "thread_hyp_worker_dead"
            action["hyp_id"] = self.hyp_id
            self.queue_master.put(action)
        except Exception as e:
            logs.exception_id.debug("0067")
            logs.workers.error(
                "General error in disconnecting hypervisor {} in working thread: {}".format(
                    self.hyp_id, e
                )
            )

    def get_queue_items(self):
        # Get the list with this format {“desktop_id”: “UUID-UUID…”, “event”: “Starting”, “position”: 14}
        items = list(self.queue_actions.queue)
        # Order them by their priority and then by the order in the queue
        sorted_items = sorted(items, key=lambda x: (x[0], x[1]))
        positioned_items = [
            {
                "priority": item[0],
                "order_in_queue": item[1],
                "event": item[2]["type"],
                "desktop_id": item[2]["id_domain"],
                "position": idx
                + 1,  # Adding 1 to make position human-readable (1-based index)
            }
            for idx, item in enumerate(sorted_items)
        ]
        return positioned_items

    def update_desktops_queue(self, positioned_items=[]):
        if positioned_items == []:
            return
        parsed_positioned_items = [
            {
                "desktop_id": item["desktop_id"],
                "event": ITEMS_STATUS_MAP.get(item["event"], "Unknown"),
                "position": item["position"],
            }
            for item in positioned_items
            if item["event"] in ITEMS_STATUS_MAP.keys()
        ]

        try:
            api_client.put(
                "/notify/desktops/queue",
                data=parsed_positioned_items,
                timeout=0.0000000001,
            )
        except requests_ReadTimeout:
            pass
        except Exception as e:
            logs.workers.error(f"Error updating desktops queue: {e}")
