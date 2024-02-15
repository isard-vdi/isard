# Copyright 2021 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3


import pprint
import queue
import threading
import traceback
from datetime import datetime
from time import sleep

from engine.config import (
    POLLING_INTERVAL_BACKGROUND,
    STATUS_POLLING_INTERVAL,
    TEST_HYP_FAIL_INTERVAL,
    TIME_BETWEEN_POLLING,
)
from engine.controllers.broom import launch_thread_broom
from engine.controllers.events_recolector import launch_thread_hyps_event
from engine.controllers.ui_actions import UiActions
from engine.models.hypervisor_orchestrator import HypervisorsOrchestratorThread
from engine.models.pool_hypervisors import PoolDiskoperations, PoolHypervisors
from engine.services.db import (
    delete_table_item,
    get_domain,
    get_domain_hyp_started,
    get_hypers_ids_with_status,
    get_if_all_disk_template_created,
    remove_domain,
    update_domain_history_from_id_domain,
)
from engine.services.db.db import (
    new_rethink_connection,
    update_table_dict,
    update_table_field,
)
from engine.services.db.domains import (
    update_domain_start_after_created,
    update_domain_status,
)
from engine.services.db.hypervisors import update_all_hyps_status
from engine.services.db.storage_pool import get_storage_pool_ids
from engine.services.lib.functions import (
    QueuesThreads,
    clean_intermediate_status,
    clean_started_without_hyp,
    domain_status_from_started_to_unknown,
    get_threads_running,
    get_tid,
)
from engine.services.lib.status import get_next_disk, get_next_hypervisor
from engine.services.lib.telegram import telegram_send_thread
from engine.services.log import logs
from engine.services.threads.download_thread import launch_thread_download_changes
from isardvdi_common.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from rethinkdb import r
from tabulate import tabulate

WAIT_HYP_ONLINE = 2.0


class Engine(object):
    """Main class that control and launch all threads.
    Main thread ThreadBackground is launched and control all threads

    status_polling_interval: seconds between polling
                             to hypervisor for statistics
                             and status (cpu, memory, domains...)

    test_hyp_fail_interval: seconds waiting between test if all is ok
                            in queue of actions in ThreadBackground"""

    def __init__(
        self,
        launch_threads=True,
        with_status_threads=True,
        status_polling_interval=STATUS_POLLING_INTERVAL,
        test_hyp_fail_interval=TEST_HYP_FAIL_INTERVAL,
    ):
        logs.main.info("MAIN TID: {}".format(get_tid()))

        self.time_between_polling = TIME_BETWEEN_POLLING
        self.polling_interval_background = POLLING_INTERVAL_BACKGROUND
        self.with_status_threads = with_status_threads

        self.q = QueuesThreads()
        self.t_workers = {}
        self.t_status = {}
        self.pools = {}
        self.diskoperations_pools = {}
        self.t_disk_operations = {}
        self.q_disk_operations = {}
        self.t_orchestrator = None
        self.t_events = None
        self.t_changes_domains = None
        self.t_broom = None
        self.t_background = None
        self.t_downloads_changes = None
        self.quit = False

        self.threads_info_main = {}
        self.threads_info_hyps = {}
        self.hypers_disk_operations_tested = []

        self.num_workers = 0
        self.threads_main_started = False

        self.STATUS_POLLING_INTERVAL = status_polling_interval
        self.TEST_HYP_FAIL_INTERVAL = test_hyp_fail_interval

        # delete hypervisors in status deleting
        hypers_to_delete = get_hypers_ids_with_status("Deleting")
        for hyp_id_delete in hypers_to_delete:
            logs.main.error(
                f"Deleting from database hypervisor {hyp_id_delete} with status Deleting"
            )
            delete_table_item("hypervisors", hyp_id_delete)

        update_all_hyps_status(reset_status="Offline")
        if launch_threads is True:
            self.launch_thread_background_polling()

    def launch_thread_background_polling(self):
        self.t_background = self.ThreadBackground(name="manager_pooling", parent=self)
        self.t_background.daemon = True
        self.t_background.start()

    class ThreadBackground(threading.Thread):
        def __init__(self, name, parent):
            threading.Thread.__init__(self)
            self.name = name
            self.manager = parent
            self.stop = False
            # self.manager = parent
            self.hyps_running = []

        def set_parent(self, parent):
            self.manager = parent

        def check_and_start_hyps(self):
            pass

        def run(self):
            self.tid = get_tid()
            logs.main.info(
                "starting thread background: {} (TID {})".format(self.name, self.tid)
            )
            q = self.manager.q.background
            first_loop = True
            pool_id = "default"
            # can't launch downloads if download changes thread is not ready and hyps are not online
            update_table_field(
                "hypervisors_pools", pool_id, "download_changes", "Stopped"
            )

            # if domains have intermedite states (updating, download_aborting...)
            # to Failed, Stopped or Delete
            clean_intermediate_status()

            # if domains have no hyp_started if status if Started, Stopping... must be Failed
            clean_started_without_hyp()

            # now, all domains that has started change to Unknown waiting to hypervisor online that will change
            # to Started/Stopped...
            domain_status_from_started_to_unknown()

            l_old_threads_running = False
            threads_running = False
            next_available = False
            last_workers_started = []
            while self.manager.quit is False:
                ####################################################################
                ### MAIN LOOP ######################################################

                # ONLY FOR DEBUG
                if threads_running is not False:
                    l_old_threads_running = l_threads_running.copy()
                threads_running = get_threads_running()
                l_threads_running = {
                    t.ident: [
                        t.name,
                        t.native_id,
                        t.tid if hasattr(t, "tid") else 0,
                        t.ident,
                    ]
                    for t in threads_running
                }
                if l_old_threads_running is not False:
                    if (
                        len(
                            set(l_old_threads_running.keys()).symmetric_difference(
                                set(l_threads_running.keys())
                            )
                        )
                        > 0
                    ):
                        logs.main.info(
                            "#####  CHANGES IN THREADS THREADS ##################"
                        )
                        threads_started = [
                            l_threads_running[k]
                            for k in set(l_threads_running.keys()).difference(
                                set(l_old_threads_running.keys())
                            )
                        ]
                        threads_dead = [
                            l_old_threads_running[k]
                            for k in set(l_old_threads_running.keys()).difference(
                                set(l_threads_running.keys())
                            )
                        ]

                        table = [["new"] + l for l in threads_started] + [
                            ["dead"] + l for l in threads_dead
                        ]
                        table_tabulated = "\n" + tabulate(
                            table,
                            headers=["state", "name", "tid", "id"],
                            tablefmt="github",
                        )
                        logs.threads.info(table_tabulated)

                        last_workers_started = workers_started = [
                            t[0].split("_")[1]
                            for t in threads_started
                            if t[0].startswith("worker_")
                        ]
                        diskop_started = [
                            t[0].split("_")[1]
                            for t in threads_started
                            if t[0].startswith("diskop_")
                        ]
                        # Sometimes engine starts with no hypervisors available
                        # Afterwards we are testing if hypervisors are available through balancer
                        # if not len(workers_started) or not len(diskop_started):
                        #     telegram_send_thread("DOWN", "No hypervisors available")
                        if len(workers_started) != len(diskop_started):
                            telegram_send_thread(
                                "WARN",
                                f"Engine Workers threads ({workers_started}) and diskop threads ({diskop_started}) are not equal",
                            )
                            next_available = False  # Just to check afterwards if we have hypervisors available and send an UP

                        for t in threads_dead:
                            if t[0].startswith("worker_"):
                                update_table_dict(
                                    "hypervisors",
                                    t[0].split("_")[1],
                                    {"cap_status": {"hypervisor": False}},
                                )
                                telegram_send_thread(
                                    "WARN",
                                    f"Hypervisor {t[0].split('_')[1]} worker is dead\n",
                                )
                                next_available = False  # Just to check afterwards if we have hypervisors available and send an UP
                            if t[0].startswith("diskop_"):
                                update_table_dict(
                                    "hypervisors",
                                    t[0].split("_")[1],
                                    {"cap_status": {"disk_operations": False}},
                                )
                                telegram_send_thread(
                                    "WARN",
                                    f"Hypervisor {t[0].split('_')[1]} disk_operations is dead\n",
                                )
                                next_available = False  # Just to check afterwards if we have hypervisors available and send an UP

                # Check viewers in hypers started
                for w in last_workers_started:
                    try:
                        result = self.manager.t_workers[w].h.get_hyp_video_status()
                        update_table_field(
                            "hypervisors",
                            w,
                            "viewer_status",
                            result,
                        )
                    except Exception as e:
                        logs.main.error(e)
                        logs.main.error(
                            f"Error updating viewer status for hypervisor {w}"
                        )
                        continue
                    for k, v in result.items():
                        if v is False:
                            telegram_send_thread(
                                "DOWN",
                                f"Video {k} connection to hypervisor {w} not functional",
                            )

                disk = get_next_disk()
                virt = get_next_hypervisor()
                if next_available is True:
                    if not disk and not virt:
                        telegram_send_thread(
                            "DOWN",
                            "No hypervisor for virtualization neither disk operations available.",
                        )
                    elif not virt:
                        telegram_send_thread(
                            "DOWN", "No hypervisor for virtualization available."
                        )
                    elif not disk:
                        telegram_send_thread(
                            "DOWN", "No disk operations hypervisor available."
                        )
                    if not disk or not virt:
                        next_available = False
                else:
                    if disk and virt:
                        telegram_send_thread(
                            "UP",
                            f"Engine threads changes detected, workers started: {workers_started}, diskop started: {diskop_started}",
                        )
                        next_available = True
                # pprint.pprint(threads_running)
                # self.manager.update_info_threads_engine()

                # Threads that must be running always, with or withouth hypervisor:
                # - changes_hyp
                # - changes_domains
                # - downloads_changes
                # - broom
                # - events

                # Threads that depends on hypervisors availavility:
                # - disk_operations
                # - for every hypervisor:
                #     - worker
                #     - status

                # LAUNCH MAIN THREADS
                if first_loop is True:
                    update_table_field(
                        "engine", "engine", "status_all_threads", "Starting"
                    )

                    # launch changes_domains_thread
                    self.manager.t_changes_domains = self.manager.DomainsChangesThread(
                        "changes_domains", self.manager
                    )
                    self.manager.t_changes_domains.daemon = True
                    self.manager.t_changes_domains.start()

                    # Hypervisors balancer pools
                    self.manager.pools["default"] = PoolHypervisors("default")
                    # Diskoperations balancer pools
                    for pool_id in get_storage_pool_ids():
                        self.manager.diskoperations_pools[pool_id] = PoolDiskoperations(
                            pool_id
                        )

                    # launch downloads changes thread
                    self.manager.t_downloads_changes = launch_thread_download_changes(
                        self.manager,
                        self.manager.q.workers,
                        self.manager.t_disk_operations,
                    )

                    # launch brom thread
                    self.manager.t_broom = launch_thread_broom(self.manager)

                    # launch events thread
                    logs.main.debug("launching hypervisor events thread")
                    self.manager.t_events = launch_thread_hyps_event()

                    # launch orchestrator thread
                    self.manager.t_orchestrator = HypervisorsOrchestratorThread(
                        "orchestrator",
                        t_workers=self.manager.t_workers,
                        t_events=self.manager.t_events,
                        t_disk_operations=self.manager.t_disk_operations,
                        q_disk_operations=self.manager.q_disk_operations,
                        queues_object=self.manager.q,
                    )
                    self.manager.t_orchestrator.daemon = True
                    self.manager.t_orchestrator.start()

                    logs.main.info("THREADS LAUNCHED FROM BACKGROUND THREAD")
                    update_table_field(
                        "engine", "engine", "status_all_threads", "Starting"
                    )

                    while True:
                        # wait all
                        sleep(0.1)
                        self.manager.update_info_threads_engine()

                        # if len(self.manager.threads_info_main['not_defined']) > 0 and len(self.manager.dict_hyps_ready) == 0:
                        if (
                            len(self.manager.threads_info_main["not_defined"]) > 0
                            or len(self.manager.threads_info_main["dead"]) > 0
                        ):
                            print("MAIN THREADS starting, wait a second extra")
                            sleep(1)
                            self.manager.update_info_threads_engine()
                            pprint.pprint(self.manager.threads_info_main)
                            # self.test_hyps_and_start_threads()
                        if (
                            len(self.manager.threads_info_main["not_defined"]) == 0
                            and len(self.manager.threads_info_main["dead"]) == 0
                        ):
                            update_table_field(
                                "engine", "engine", "status_all_threads", "Started"
                            )
                            self.manager.threads_main_started = True
                            break

                # Test hypervisor disk operations
                # Create Test disk in hypervisor disk operations
                if first_loop is True:
                    first_loop = False

                self.manager.update_info_threads_engine()
                if len(self.manager.threads_info_hyps["not_defined"]) > 0:
                    logs.main.error(
                        "something was wrong when launching threads for hypervisors, threads not defined"
                    )
                    logs.main.error(pprint.pformat(self.manager.threads_info_hyps))
                if len(self.manager.threads_info_hyps["dead"]) > 0:
                    logs.main.error(
                        "something was wrong when launching threads for hypervisors, threads are dead"
                    )
                    logs.main.error(pprint.pformat(self.manager.threads_info_hyps))
                if (
                    len(self.manager.threads_info_hyps["dead"]) == 0
                    and len(self.manager.threads_info_hyps["not_defined"]) == 0
                ):
                    pass

                try:
                    if len(self.manager.t_workers) == 0:
                        timeout_queue = WAIT_HYP_ONLINE
                        logs.main.debug("WAITING HYPERVISORS ONLINE...")
                    else:
                        timeout_queue = TEST_HYP_FAIL_INTERVAL

                    # ACTIONS TO DO IN MAIN THREAD WITH QUEUE
                    action = q.get(timeout=timeout_queue)
                    # STOP
                    if action["type"] == "stop":
                        self.manager.quit = True
                        logs.main.info("engine end")

                except queue.Empty:
                    pass
                except Exception as e:
                    logs.exception_id.debug("0025")
                    logs.main.error(e)
                    return False

    class DomainsChangesThread(threading.Thread):
        def __init__(self, name, parent):
            threading.Thread.__init__(self)
            self.manager = parent
            self.name = name
            self.stop = False
            self.r_conn = False

        def run(self):
            self.tid = get_tid()
            logs.changes.info(
                "starting thread: {} (TID {})".format(self.name, self.tid)
            )
            logs.changes.debug(
                "^^^^^^^^^^^^^^^^^^^ DOMAIN CHANGES THREAD ^^^^^^^^^^^^^^^^^"
            )
            ui = UiActions(self.manager)

            self.r_conn = new_rethink_connection()

            cursor = (
                r.table("domains")
                .pluck("id", "kind", "status", "detail")
                .merge({"table": "domains"})
                .changes()
                .union(
                    r.table("engine")
                    .pluck("threads", "status_all_threads")
                    .merge({"table": "engine"})
                    .changes()
                )
                .run(self.r_conn)
            )

            for c in cursor:
                try:
                    if self.stop is True:
                        break

                    if c.get("new_val", None) != None:
                        if c["new_val"]["table"] == "engine":
                            if c["new_val"]["status_all_threads"] == "Stopping":
                                break
                            else:
                                continue

                    if c["old_val"] is None:
                        domain_id_for_logs = c.get("new_val", {}).get("id", "NODOMAIN")
                        old_status_for_logs = "NONE"
                        new_status_for_logs = c.get("new_val", {}).get("status", "NONE")

                    elif c["new_val"] is None:
                        domain_id_for_logs = c.get("old_val", {}).get("id", "NODOMAIN")
                        old_status_for_logs = (
                            c.get("old_val", {}).get("status", "NONE"),
                        )
                        new_status_for_logs = "NONE"
                    else:
                        domain_id_for_logs = c.get("old_val", {}).get(
                            "id", c.get("new_val", {}).get("id", "NODOMAIN")
                        )
                        old_status_for_logs = (
                            c.get("old_val", {}).get("status", "NONE"),
                        )
                        new_status_for_logs = c.get("new_val", {}).get("status", "NONE")
                    logs.changes.debug("domain changes detected in main thread")
                    logs.changes.debug(
                        f"** {domain_id_for_logs} :: {old_status_for_logs} --> {new_status_for_logs}"
                    )

                    detail_msg_if_no_hyps_online = "No hypervisors Online in pool"
                    if self.manager.check_actions_domains_enabled() is False:
                        if c.get("new_val", None) != None:
                            if c.get("old_val", None) != None:
                                if c["new_val"]["status"][-3:] == "ing":
                                    update_domain_status(
                                        c["old_val"]["status"],
                                        c["old_val"]["id"],
                                        detail=detail_msg_if_no_hyps_online,
                                    )

                        # if no hypervisor availables no check status changes
                        continue

                    new_domain = False
                    new_status = False
                    old_status = False
                    logs.changes.debug(pprint.pformat(c))

                    # action deleted
                    if c.get("new_val", None) is None:
                        pass
                    # action created
                    if c.get("old_val", None) is None:
                        new_domain = True
                        new_status = c["new_val"]["status"]
                        domain_id = c["new_val"]["id"]
                        logs.changes.debug("domain_id: {}".format(new_domain))
                        # if engine is stopped/restarting or not hypervisors online
                        if self.manager.check_actions_domains_enabled() is False:
                            continue
                        pass

                    if (
                        c.get("new_val", None) != None
                        and c.get("old_val", None) != None
                    ):
                        old_status = c["old_val"]["status"]
                        new_status = c["new_val"]["status"]
                        new_detail = c["new_val"]["detail"]
                        domain_id = c["new_val"]["id"]
                        logs.changes.debug("domain_id: {}".format(domain_id))
                        # if engine is stopped/restarting or not hypervisors online

                        if old_status != new_status:
                            # print('&&&&&&& ID DOMAIN {} - old_status: {} , new_status: {}, detail: {}'.format(domain_id,old_status,new_status, new_detail))
                            # if new_status[-3:] == 'ing':
                            if 1 > 0:
                                date_now = datetime.now()
                                res = update_domain_history_from_id_domain(
                                    domain_id, new_status, new_detail, date_now
                                )
                                if res is False:
                                    continue
                        else:
                            # print('&&&&&&&ESTADOS IGUALES OJO &&&&&&&\n&&&&&&&& ID DOMAIN {} - old_status: {} , new_status: {}, detail: {}'.
                            #       format(domain_id,old_status,new_status,new_detail))
                            pass

                    if new_domain is True and new_status == "CreatingDiskFromScratch":
                        ui.creating_disk_from_scratch(domain_id)

                    if new_domain is True and new_status == "Creating":
                        ui.creating_disks_from_template(domain_id)

                    if new_domain is True and new_status == "CreatingAndStarting":
                        update_domain_start_after_created(domain_id)
                        ui.creating_disks_from_template(domain_id)

                        # INFO TO DEVELOPER
                        # recoger template de la que hay que derivar
                        # verificar que realmente es una template
                        # hay que recoger ram?? cpu?? o si no hay nada copiamos de la template??

                    if new_domain is True and new_status == "CreatingFromBuilder":
                        ui.creating_disk_from_virtbuilder(domain_id)

                    if (
                        (
                            old_status in ["CreatingDisk", "CreatingDiskFromScratch"]
                            and new_status == "CreatingDomain"
                        )
                        or (
                            new_domain is True
                            and new_status == "CreatingDomainFromDisk"
                        )
                        or (
                            old_status == "RunningVirtBuilder"
                            and new_status == "CreatingDomainFromBuilder"
                        )
                    ):
                        logs.changes.debug(
                            "llamo a creating_and_test_xml con domain id {}".format(
                                domain_id
                            )
                        )
                        if new_status == "CreatingDomainFromBuilder":
                            ui.creating_and_test_xml_start(
                                domain_id,
                                creating_from_create_dict=True,
                                xml_from_virt_install=True,
                                ssl=True,
                            )
                        if (
                            new_status == "CreatingDomain"
                            or new_status == "CreatingDomainFromDisk"
                        ):
                            ui.creating_and_test_xml_start(
                                domain_id, creating_from_create_dict=True, ssl=True
                            )

                    if old_status == "Stopped" and new_status == "CreatingTemplate":
                        ui.create_template_disks_from_domain(domain_id)

                    if (
                        old_status not in ["Started", "Shutting-down"]
                        and new_status == "Deleting"
                    ):
                        # or \
                        #     old_status == 'Failed' and new_status == "Deleting" or \
                        #     old_status == 'Downloaded' and new_status == "Deleting":
                        ui.deleting_disks_from_domain(domain_id)

                    if (
                        (old_status == "Stopped" and new_status == "Updating")
                        or (old_status == "Failed" and new_status == "Updating")
                        or (old_status == "Downloaded" and new_status == "Updating")
                    ):
                        ui.updating_from_create_dict(domain_id, ssl=True)

                    if (
                        old_status == "DeletingDomainDisk"
                        and new_status == "DiskDeleted"
                    ):
                        logs.changes.debug(
                            "disk deleted, mow remove domain form database"
                        )
                        remove_domain(domain_id)
                        if get_domain(domain_id) is None:
                            logs.changes.info(
                                "domain {} deleted from database".format(domain_id)
                            )
                        else:
                            update_domain_status(
                                "Failed",
                                domain_id,
                                detail="domain {} can not be deleted from database".format(
                                    domain_id
                                ),
                            )

                    if (
                        old_status == "CreatingTemplateDisk"
                        and new_status == "TemplateDiskCreated"
                    ):
                        # create_template_from_dict(dict_new_template)
                        if get_if_all_disk_template_created(domain_id):
                            ui.create_template_in_db(domain_id)
                        else:
                            # INFO TO DEVELOPER, este else no se si tiene mucho sentido, hay que hacer pruebas con la
                            # creación de una template con dos discos y ver si pasa por aquí
                            # waiting to create other disks
                            update_domain_status(
                                status="CreatingTemplateDisk",
                                id_domain=domain_id,
                                hyp_id=False,
                                detail="Waiting to create more disks for template",
                            )

                    if (old_status == "Stopped" and new_status == "StartingPaused") or (
                        old_status == "Failed" and new_status == "StartingPaused"
                    ):
                        ui.start_domain_from_id(
                            id_domain=domain_id, ssl=True, starting_paused=True
                        )

                    if (old_status == "Stopped" and new_status == "Starting") or (
                        old_status == "Failed" and new_status == "Starting"
                    ):
                        ui.start_domain_from_id(id_domain=domain_id, ssl=True)

                    if old_status == "Started" and new_status == "Shutting-down":
                        # INFO TO DEVELOPER Esto es lo que debería ser, pero hay líos con el hyp_started
                        # ui.stop_domain_from_id(id=domain_id)
                        hyp_started = get_domain_hyp_started(domain_id)
                        if hyp_started:
                            ui.shutdown_domain(id_domain=domain_id, hyp_id=hyp_started)
                        else:
                            logs.main.error(
                                "domain without hyp_started can not be stopped: {}. ".format(
                                    domain_id
                                )
                            )

                    if (
                        (old_status == "Started" and new_status == "Stopping")
                        or (old_status == "Shutting-down" and new_status == "Stopping")
                        or (old_status == "Suspended" and new_status == "Stopping")
                    ):
                        # INFO TO DEVELOPER Esto es lo que debería ser, pero hay líos con el hyp_started
                        # ui.stop_domain_from_id(id=domain_id)
                        hyp_started = get_domain_hyp_started(domain_id)
                        if hyp_started:
                            ui.stop_domain(id_domain=domain_id, hyp_id=hyp_started)
                        else:
                            logs.main.error(
                                "domain without hyp_started can not be stopped: {}. ".format(
                                    domain_id
                                )
                            )

                    if (
                        old_status
                        in [
                            "Started",
                            "Shutting-down",
                            "Suspended",
                            "Stopping",
                        ]
                        and new_status == "Resetting"
                    ):
                        hyp_started = get_domain_hyp_started(domain_id)
                        if hyp_started:
                            ui.reset_domain(id_domain=domain_id, hyp_id=hyp_started)
                        else:
                            logs.main.error(
                                "domain without hyp_started can not be reset: {}. ".format(
                                    domain_id
                                )
                            )

                    if old_status in [
                        "Started",
                        "Shutting-down",
                        "Suspended",
                        "Stopping",
                    ] and new_status in ["Stopped"]:
                        ui.update_info_after_stopped_domain(domain_id=domain_id)

                    # when download domain or updating, status previous to stopped is CreatingDomain
                    # and we can update disk info
                    if old_status in [
                        "CreatingDomain",
                    ] and new_status in ["Stopped"]:
                        ui.update_info_after_stopped_domain(domain_id=domain_id)

                    if (
                        old_status == "Started" and new_status == "StoppingAndDeleting"
                    ) or (
                        old_status == "Suspended"
                        and new_status == "StoppingAndDeleting"
                    ):
                        # INFO TO DEVELOPER Esto es lo que debería ser, pero hay líos con el hyp_started
                        # ui.stop_domain_from_id(id=domain_id)
                        hyp_started = get_domain_hyp_started(domain_id)
                        print(hyp_started)
                        ui.stop_domain(
                            id_domain=domain_id,
                            hyp_id=hyp_started,
                            delete_after_stopped=True,
                        )

                    if new_domain is False and new_status == "ForceDeleting":
                        ui.force_deleting(domain_id, old_status)

                except Exception as e:
                    logs.exception_id.debug("0072")
                    logs.main.critical("EXCEPTION UNEXPECTED IN CHANGES_DOMAIN THREAD")
                    logs.main.critical(e)
                    logs.main.critical(
                        "Traceback: \n .{}".format(traceback.format_exc())
                    )

            logs.main.info("finalished thread domain changes")

    def check_actions_domains_enabled(self):
        if len(self.t_workers) > 0 and self.threads_main_started is True:
            return True
        else:
            return False

    def update_info_threads_engine(self):
        d_mains = {}
        alive = []
        dead = []
        not_defined = []
        # events,broom
        for name in [
            "events",
            "broom",
            "downloads_changes",
            "orchestrator",
            "changes_domains",
        ]:
            try:
                (
                    alive.append(name)
                    if self.__getattribute__("t_" + name).is_alive()
                    else dead.append(name)
                )
            except:
                # thread not defined
                not_defined.append(name)

        d_mains["alive"] = alive
        d_mains["dead"] = dead
        d_mains["not_defined"] = not_defined
        self.threads_info_main = d_mains.copy()

        d_hyps = {}
        alive = []
        dead = []
        not_defined = []
        for name in ["workers", "status", "disk_operations"]:
            for hyp, t in self.__getattribute__("t_" + name).items():
                try:
                    (
                        alive.append(name + "_" + hyp)
                        if t.is_alive()
                        else dead.append(name + "_" + hyp)
                    )
                except:
                    not_defined.append(name)

        d_hyps["alive"] = alive
        d_hyps["dead"] = dead
        d_hyps["not_defined"] = not_defined
        self.threads_info_hyps = d_hyps.copy()
        update_table_field("engine", "engine", "threads_info_main", d_mains)
        update_table_field("engine", "engine", "threads_info_hyps", d_hyps)

        return True

    def stop_threads(self):
        # events and broom
        # try:
        self.t_events.stop = True
        while True:
            if self.t_events.is_alive() is False:
                break
            sleep(0.1)
        # except TypeError:
        #    pass
        self.t_broom.stop = True
        # operations / status
        for k, v in self.t_disk_operations.items():
            v.stop = True
        for k, v in self.t_workers.items():
            v.stop = True
        for k, v in self.t_status.items():
            v.stop = True

        # changes
        update_table_field("engine", "engine", "status_all_threads", "Stopping")
