# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import threading

from engine.models.hyp import hyp
from engine.services.db import get_domains_started_in_hyp, update_all_domains_status
from engine.services.db.domains import update_domain_status
from engine.services.db.hypervisors import (
    get_hyp_hostname_from_id,
    update_hyp_status,
    update_hyp_thread_status,
)
from engine.services.lib.functions import (
    PriorityQueueIsard,
    dict_domain_libvirt_state_to_isard_state,
    state_and_cause_to_str,
)
from engine.services.log import *

TIMEOUT_QUEUES = float(CONFIG_DICT["TIMEOUTS"]["timeout_queues"])
TIMEOUT_BETWEEN_RETRIES_HYP_IS_ALIVE = max(
    2.0, float(CONFIG_DICT["TIMEOUTS"]["timeout_between_retries_hyp_is_alive"])
)
RETRIES_HYP_IS_ALIVE = max(8, int(CONFIG_DICT["TIMEOUTS"]["retries_hyp_is_alive"]))


def threading_enumerate():
    # time.sleep(0.5)
    e = threading.enumerate()
    l = [t._Thread__name for t in e]
    l.sort()
    for i in l:
        logs.main.debug("Thread running: {}".format(i))
    return e


def launch_thread_worker(hyp_id, q_event_register, queue_master):
    log.debug("launching thread wordker for hypervisor: {}".format(hyp_id))
    q = PriorityQueueIsard()
    update_hyp_thread_status("worker", hyp_id, "Starting")
    # t = threading.Thread(name='worker_'+hyp_id,target=hyp_worker_thread, args=(hyp_id,q,queue_master))
    t = HypWorkerThread(
        name="worker_" + hyp_id,
        hyp_id=hyp_id,
        queue_actions=q,
        queue_master=queue_master,
        q_event_register=q_event_register,
    )
    t.daemon = True
    t.start()
    return t, q


def hyp_from_hyp_id(hyp_id):
    """Create a hypervisor connection object from a hypervisor ID."""
    try:
        (
            host,
            port,
            user,
            nvidia_enabled,
            init_vgpu_profiles,
        ) = get_hyp_hostname_from_id(hyp_id)
        h = hyp(hyp_id, host, user=user, port=port)
        return h
    except:
        return False


def set_domains_coherence(dict_hyps_ready):
    for hyp_id, hostname in dict_hyps_ready.items():
        hyp_obj = hyp_from_hyp_id(hyp_id)
        if not hyp_obj:
            log.error(f"Failed to create hypervisor connection for {hyp_id}")
            update_hyp_status(hyp_id, "Error")
            continue

        try:
            hyp_obj.get_domains()
        except Exception as e:
            log.error(f"hypervisor {hyp_id} can not get domains: {e}")
            update_hyp_status(hyp_id, "Error")
            # Disconnect to prevent connection leak
            try:
                hyp_obj.disconnect()
            except Exception:
                pass
            continue

        # update domain_status
        update_all_domains_status(reset_status="Stopped", from_status=["Starting"])
        update_all_domains_status(reset_status="Started", from_status=["Stopping"])
        update_all_domains_status(reset_status="Started", from_status=["Shutdown"])
        domains_started_in_rethink = get_domains_started_in_hyp(hyp_id)
        domains_are_started = []

        for domain_name, domain_obj in hyp_obj.domains.items():
            domain_state_libvirt = domain_obj.state()
            state, reason = state_and_cause_to_str(
                domain_state_libvirt[0], domain_state_libvirt[1]
            )
            status_isard = dict_domain_libvirt_state_to_isard_state[state]
            update_domain_status(
                status=status_isard, id_domain=domain_name, hyp_id=hyp_id, detail=reason
            )
            domains_are_started.append(domain_name)

        if len(domains_started_in_rethink) > 0:
            domains_are_shutdown = list(
                set(domains_started_in_rethink).difference(set(domains_are_started))
            )
            for domain_stopped in domains_are_shutdown:
                update_domain_status(
                    status="Stopped", id_domain=domain_stopped, hyp_id=""
                )
        # TODO INFO TO DEVELOPER: faltaría revisar que ningún dominio está duplicado en y started en dos hypervisores
        # a nivel de libvirt, porque a nivel de rethink es imposible, y si pasa poner un erroraco gigante
        # a parte de dejarlo en unknown

        update_hyp_status(hyp_id, "ReadyToStart")

        # Disconnect after use to prevent connection leak
        try:
            hyp_obj.disconnect()
        except Exception as e:
            log.warning(f"Error disconnecting from hypervisor {hyp_id}: {e}")


# IMPORT Thread Classes HERE
from engine.services.threads.disk_operations_thread import DiskOperationsThread
from engine.services.threads.hyp_worker_thread import HypWorkerThread
