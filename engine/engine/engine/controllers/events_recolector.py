# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# !/usr/bin/python3
#
#
#
##############################################################################
# Start off by implementing a general purpose event loop for anyone's use
##############################################################################

import atexit
import queue
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

import libvirt
from engine.controllers.ui_actions import Q_PRIORITY_PERSONAL_UNIT
from engine.models.rethink_hyp_event import RethinkHypEvent
from engine.services.db import (
    domain_get_vgpu_info,
    get_domain,
    get_domain_hyp_started_and_status_and_detail,
    get_domain_status,
    get_hyp_hostname_user_port_from_id,
    get_id_hyp_from_uri,
    update_domain_status,
    update_uri_hyp,
    update_vgpu_info_if_stopped,
    update_vgpu_uuid_domain_action,
)
from engine.services.lib.functions import PriorityQueueIsard, get_tid, hostname_to_uri
from engine.services.log import *

TIMEOUT_QUEUE_REGISTER_EVENTS = 1
NUM_TRY_REGISTER_EVENTS = 5
SLEEP_BETWEEN_TRY_REGISTER_EVENTS = 1.0

# =============================================================================
# Async Event Processing Configuration
# =============================================================================

# Maximum number of concurrent event processor threads
EVENT_PROCESSOR_MAX_WORKERS = 50

# Thread pool for processing domain events asynchronously
# This prevents slow database operations from blocking the libvirt event loop
_event_processor_pool = ThreadPoolExecutor(
    max_workers=EVENT_PROCESSOR_MAX_WORKERS, thread_name_prefix="event_processor"
)


def _shutdown_event_processor_pool():
    """Shutdown the event processor pool gracefully."""
    try:
        _event_processor_pool.shutdown(wait=False)
    except Exception:
        pass


# Register shutdown handler for graceful cleanup
atexit.register(_shutdown_event_processor_pool)

# Reference: https://github.com/libvirt/libvirt-python/blob/master/examples/event-test.py
import pprint


def virEventLoopNativeRun(stop):
    while stop[0] is False:
        libvirt.virEventRunDefaultImpl()


# Spawn a background thread to run the event loop
# def virEventLoopPureStart(stop):
#     #    global eventLoopThread
#     virEventLoopPureRegister()
#     eventLoopThread = threading.Thread(target=virEventLoopPureRun, name="libvirtEventLoop")
#     eventLoopThread.setDaemon(True)
#     eventLoopThread.start()


# def virEventLoopNativeStart(hostname='unknowhost'):
#     global eventLoopThread
#     libvirt.virEventRegisterDefaultImpl()
#     eventLoopThread = threading.Thread(target=virEventLoopNativeRun, name="EventLoop_{}".format(hostname))
#     eventLoopThread.setDaemon(True)
#     eventLoopThread.start()
#
def virEventLoopNativeStart(stop):
    libvirt.virEventRegisterDefaultImpl()
    eventLoopThread = threading.Thread(
        target=virEventLoopNativeRun, name="EventLoop", args=(stop,)
    )
    eventLoopThread.setDaemon(True)
    eventLoopThread.start()
    return eventLoopThread


##########################################################################
# Everything that now follows is a simple demo of domain lifecycle events
##########################################################################


def domEventToString(event):
    # from https://github.com/libvirt/libvirt-python/blob/master/examples/event-test.py
    domEventStrings = (
        "Defined",
        "Undefined",
        "Started",
        "Suspended",
        "Resumed",
        "Stopped",
        "Shutdown",
        "PMSuspended",
        "Crashed",
    )
    return domEventStrings[event]


def domDetailToString(event, detail):
    # from https://github.com/libvirt/libvirt-python/blob/master/examples/event-test.py
    DOM_EVENTS = (
        ("Defined", ("Added", "Updated", "Renamed", "Snapshot")),
        ("Undefined", ("Removed", "Renamed")),
        ("Started", ("Booted", "Migrated", "Restored", "Snapshot", "Wakeup")),
        (
            "Suspended",
            (
                "Paused",
                "Migrated",
                "IOError",
                "Watchdog",
                "Restored",
                "Snapshot",
                "API error",
                "Postcopy",
                "Postcopy failed",
            ),
        ),
        ("Resumed", ("Unpaused", "Migrated", "Snapshot", "Postcopy")),
        (
            "Stopped",
            (
                "Shutdown",
                "Destroyed",
                "Crashed",
                "Migrated",
                "Saved",
                "Failed",
                "Snapshot",
                "Daemon",
            ),
        ),
        ("Shutdown", ("Finished", "On guest request", "On host request")),
        ("PMSuspended", ("Memory", "Disk")),
        ("Crashed", ("Panicked",)),
    )
    try:
        return DOM_EVENTS[event][1][detail]
    except Exception as e:
        logs.exception_id.debug("0004")
        logs.status.error(
            f"Detail not defined in DOM_EVENTS. index_event:{event}, index_detail{detail}"
        )
        logs.status.error(e)
        return "Detail undefined"


def blockJobTypeToString(type):
    blockJobTypes = (
        "unknown",
        "Pull",
        "Copy",
        "Commit",
        "ActiveCommit",
    )
    return blockJobTypes[type]


def blockJobStatusToString(status):
    blockJobStatus = (
        "Completed",
        "Failed",
        "Canceled",
        "Ready",
    )
    return blockJobStatus[status]


def agentLifecycleStateToString(state):
    agentStates = (
        "unknown",
        "connected",
        "disconnected",
    )
    return agentStates[state]


def agentLifecycleReasonToString(reason):
    agentReasons = (
        "unknown",
        "domain started",
        "channel event",
    )
    return agentReasons[reason]


def myDomainEventCallback1(conn, dom, event, detail, opaque):
    logs.status.debug(
        "myDomainEventCallback1 EVENT: Domain %s(%s) %s %s"
        % (
            dom.name(),
            dom.ID(),
            domEventToString(event),
            domDetailToString(event, detail),
        )
    )


def myDomainEventGraphicsCallback(
    conn, dom, phase, localAddr, remoteAddr, authScheme, subject, opaque
):
    logs.status.debug(
        "myDomainEventGraphicsCallback: Domain %s(%s) %d %s"
        % (dom.name(), dom.ID(), phase, authScheme)
    )
    # logs.status.debug("localAddr: {},remoteAddr: {}, phase:{}, subject:{}" % (localAddr, remoteAddr, phase, str(type(subject))))


def myDomainEventRebootCallback(conn, dom, opaque):
    logs.status.debug(
        "myDomainEventRebootCallback: Domain %s(%s)" % (dom.name(), dom.ID())
    )


def myDomainEventRTCChangeCallback(conn, dom, utcoffset, opaque):
    logs.status.debug(
        "myDomainEventRTCChangeCallback: Domain %s(%s) %d"
        % (dom.name(), dom.ID(), utcoffset)
    )


def myDomainEventWatchdogCallback(conn, dom, action, opaque):
    logs.status.debug(
        "myDomainEventWatchdogCallback: Domain %s(%s) %d"
        % (dom.name(), dom.ID(), action)
    )


def myDomainEventIOErrorCallback(conn, dom, srcpath, devalias, action, opaque):
    logs.status.error(
        "myDomainEventIOErrorCallback: Domain %s(%s) %s %s %d"
        % (dom.name(), dom.ID(), srcpath, devalias, action)
    )


def myDomainEventIOErrorReasonCallback(
    conn, dom, srcpath, devalias, action, reason, opaque
):
    logs.status.debug(
        "myDomainEventIOErrorReasonCallback: Domain %s(%s) %s %s %d %s"
        % (dom.name(), dom.ID(), srcpath, devalias, action, reason)
    )


def myDomainEventControlErrorCallback(conn, dom, opaque):
    logs.status.debug(
        "myDomainEventControlErrorCallback: Domain %s(%s)" % (dom.name(), dom.ID())
    )


def myDomainEventBlockJobCallback(conn, dom, disk, type, status, opaque):
    logs.status.debug(
        "myDomainEventBlockJobCallback: Domain %s(%s) %s on disk %s %s"
        % (
            dom.name(),
            dom.ID(),
            blockJobTypeToString(type),
            disk,
            blockJobStatusToString(status),
        )
    )


def myDomainEventDiskChangeCallback(
    conn, dom, oldSrcPath, newSrcPath, devAlias, reason, opaque
):
    logs.status.debug(
        "myDomainEventDiskChangeCallback: Domain %s(%s) disk change oldSrcPath: %s newSrcPath: %s devAlias: %s reason: %s"
        % (dom.name(), dom.ID(), oldSrcPath, newSrcPath, devAlias, reason)
    )


def myDomainEventTrayChangeCallback(conn, dom, devAlias, reason, opaque):
    logs.status.debug(
        "myDomainEventTrayChangeCallback: Domain %s(%s) tray change devAlias: %s reason: %s"
        % (dom.name(), dom.ID(), devAlias, reason)
    )


def myDomainEventPMWakeupCallback(conn, dom, reason, opaque):
    logs.status.debug(
        "myDomainEventPMWakeupCallback: Domain %s(%s) system pmwakeup"
        % (dom.name(), dom.ID())
    )


def myDomainEventPMSuspendCallback(conn, dom, reason, opaque):
    logs.status.debug(
        "myDomainEventPMSuspendCallback: Domain %s(%s) system pmsuspend"
        % (dom.name(), dom.ID())
    )


def myDomainEventBalloonChangeCallback(conn, dom, actual, opaque):
    logs.status.debug(
        "myDomainEventBalloonChangeCallback: Domain %s(%s) %d"
        % (dom.name(), dom.ID(), actual)
    )


def myDomainEventPMSuspendDiskCallback(conn, dom, reason, opaque):
    logs.status.debug(
        "myDomainEventPMSuspendDiskCallback: Domain %s(%s) system pmsuspend_disk"
        % (dom.name(), dom.ID())
    )


def myDomainEventDeviceRemovedCallback(conn, dom, dev, opaque):
    logs.status.debug(
        "myDomainEventDeviceRemovedCallback: Domain %s(%s) device removed: %s"
        % (dom.name(), dom.ID(), dev)
    )


def myDomainEventBlockJob2Callback(conn, dom, disk, type, status, opaque):
    logs.status.debug(
        "myDomainEventBlockJob2Callback: Domain %s(%s) %s on disk %s %s"
        % (
            dom.name(),
            dom.ID(),
            blockJobTypeToString(type),
            disk,
            blockJobStatusToString(status),
        )
    )


def myDomainEventTunableCallback(conn, dom, params, opaque):
    logs.status.debug(
        "myDomainEventTunableCallback: Domain %s(%s) %s"
        % (dom.name(), dom.ID(), params)
    )


def myDomainEventDeviceAddedCallback(conn, dom, dev, opaque):
    logs.status.debug(
        "myDomainEventDeviceAddedCallback: Domain %s(%s) device added: %s"
        % (dom.name(), dom.ID(), dev)
    )


def myDomainEventMigrationIteration(conn, dom, iteration, opaque):
    logs.status.debug(
        "myDomainEventMigrationIteration: Domain %s(%s) started migration iteration %d"
        % (dom.name(), dom.ID(), iteration)
    )


##########################################################################
# Network events
##########################################################################
def netEventToString(event):
    netEventStrings = (
        "Defined",
        "Undefined",
        "Started",
        "Stopped",
    )
    return netEventStrings[event]


def netDetailToString(event, detail):
    netEventStrings = (
        ("Added",),
        ("Removed",),
        ("Started",),
        ("Stopped",),
    )
    return netEventStrings[event][detail]


def myNetworkEventLifecycleCallback(conn, net, event, detail, opaque):
    logs.status.debug(
        "myNetworkEventLifecycleCallback: Network %s %s %s"
        % (net.name(), netEventToString(event), netDetailToString(event, detail))
    )


##########################################################################
# Set up and run the program
##########################################################################


def myConnectionCloseCallback(conn, reason, opaque):
    reasonStrings = (
        "Error",
        "End-of-file",
        "Keepalive",
        "Client",
    )
    logs.status.debug(
        "myConnectionCloseCallback: %s: %s" % (conn.getURI(), reasonStrings[reason])
    )
    run = False


##########################################################################
# New Code for IsardLib
##########################################################################


def _process_domain_event_async(conn_uri, dom_name, event, detail, opaque, event_time):
    """Process a domain event asynchronously.

    This function contains the actual event processing logic, moved out of
    the callback to allow non-blocking execution in a thread pool.

    Args:
        conn_uri: The libvirt connection URI
        dom_name: The domain name
        event: The event type (integer)
        detail: The event detail (integer)
        opaque: Opaque data passed to callback
        event_time: Timestamp when event was received
    """
    try:
        dom_id = dom_name
        hyp_id = get_id_hyp_from_uri(conn_uri)

        dict_event = {
            "domain": dom_id,
            "hyp_id": hyp_id,
            "event": domEventToString(event),
            "detail": domDetailToString(event, detail),
            "when": event_time,
        }

        logs.status.info(
            "EVENT: {domain} - {event} ({detail}) - {hyp}".format(
                domain=dom_id,
                event=dict_event["event"],
                detail=dict_event["detail"],
                hyp=hyp_id,
            )
        )

        results = get_domain_hyp_started_and_status_and_detail(dom_id)
        if results == {}:
            logs.status.debug("domain {} not in database, was deleted".format(dom_id))
            return
        domain_status = results.get("status", None)
        domain_hyp_started = results.get("hyp_started", None)

        # Skip event if domain hyp_started and event hyp_id is not the same
        if not (
            domain_hyp_started is None
            or domain_hyp_started == ""
            or domain_hyp_started == False
        ):
            if hyp_id != domain_hyp_started:
                logs.status.warning(
                    "Received event {} in hypervisor {}, but domain {} is started in hypervisor {}".format(
                        dict_event["event"],
                        hyp_id,
                        dom_id,
                        domain_hyp_started,
                    )
                )
                return

        if domain_status != None:
            if hyp_id is None or hyp_id == "":
                logs.status.debug(
                    "event in Hypervisor not in database with uri. Domain id:{}, uri:{}".format(
                        dom_id, conn_uri
                    )
                )

            if dict_event["event"] in ("Started", "Resumed"):
                if (
                    domain_status == "StartingDomainDisposable"
                    and dict_event["event"] == "Resumed"
                ):
                    logs.status.info("Event Resumed Received but waiting for Started")

                elif (
                    domain_status == "CreatingDomain"
                    and dict_event["event"] == "Started"
                ):
                    logs.status.info("Event Started Received but waiting for Paused")

                elif domain_status == "Stopped" and dict_event["event"] == "Resumed":
                    logs.status.info(
                        "Event Resumed Received but waiting for Paused to update status in database"
                    )

                elif domain_status == "Started" and dict_event["event"] == "Resumed":
                    logs.status.info(
                        "Event Resumed Received but his state is started in database"
                    )

                elif domain_status == "Starting" and dict_event["event"] == "Resumed":
                    logs.status.info(
                        "Event Resumed Received but his state is Starting in database, waiting for started"
                    )

                else:
                    try:
                        detail_event = domDetailToString(event, detail)
                        if detail_event == "Unpaused" and domain_status == "Paused":
                            status_to_update = "Started"
                        else:
                            status_to_update = domEventToString(event)
                            logs.status.info(
                                f"DOMAIN STARTED - event received: {detail_event} - {dom_id} in {hyp_id}"
                            )
                        update_domain_status(
                            id_domain=dom_id,
                            status=status_to_update,
                            hyp_id=hyp_id,
                            detail="Event received: " + detail_event,
                        )
                    except Exception as e:
                        logs.exception_id.debug("0005")
                        logs.status.error(
                            "Domain {} has been destroyed while event started is processing, typical if try domain with starting paused and destroyed".format(
                                dom_id
                            )
                        )
                        logs.status.error("Exception: " + str(e))
                        log.error("Traceback: {}".format(traceback.format_exc()))

            if dict_event["event"] in ("Suspended"):
                if (
                    domain_status == "CreatingDomain"
                    and dict_event["event"] == "Suspended"
                ):
                    logs.status.debug(
                        "Event Paused Received but waiting for Stoped to update status"
                    )
                else:
                    update_domain_status(
                        id_domain=dom_id,
                        status="Paused",
                        hyp_id=hyp_id,
                        detail="Event received: " + domDetailToString(event, detail),
                    )

            if dict_event["event"] in ("Stopped"):
                if domain_status != "Stopped" and domain_status not in [
                    "ForceDeleting"
                ]:
                    logs.status.debug(
                        "event {} ({}) in hypervisor {} changes status to Stopped in domain {}".format(
                            dict_event["event"],
                            dict_event["detail"],
                            hyp_id,
                            dict_event["domain"],
                        )
                    )

                    update_domain_status(
                        status="Stopped",
                        id_domain=dict_event["domain"],
                        hyp_id=False,
                        detail="Ready to Start",
                    )
                if dict_event["detail"] in ("Shutdown"):
                    update_vgpu_info_if_stopped(dom_id)

            if dict_event["event"] in (
                "Defined",
                "Undefined",
                "PMSuspended",
                "Crashed",
            ):
                logs.status.error(
                    "event strange, why?? event: {}, domain: {}, hyp_id: {}, detail: {}".format(
                        dict_event["event"],
                        dict_event["domain"],
                        hyp_id,
                        dict_event["detail"],
                    )
                )

        else:
            logs.status.info(
                "domain {} launch event in hyervisor {}, but id_domain is not in database".format(
                    dom_id, hyp_id
                )
            )
            logs.status.info(
                "event: {}; detail: {}".format(
                    domEventToString(event), domDetailToString(event, detail)
                )
            )

    except Exception as e:
        logs.status.error(f"Error processing domain event async: {e}")
        log.error("Traceback: {}".format(traceback.format_exc()))


def myDomainEventCallbackRethink(conn, dom, event, detail, opaque):
    """Non-blocking domain event callback.

    This callback extracts minimal information quickly and queues the actual
    processing work to a thread pool. This ensures the libvirt event loop
    is not blocked by slow database operations.
    """
    # Extract info quickly - these are fast libvirt calls
    now = int(time.time())
    dom_name = dom.name()
    conn_uri = conn.getURI()

    # Queue the actual processing to the thread pool
    _event_processor_pool.submit(
        _process_domain_event_async, conn_uri, dom_name, event, detail, opaque, now
    )


last_timestamp_event_graphics = dict()
last_chain_event_graphics = dict()
lock = threading.Lock()


def _process_graphics_event_async(
    domain_name,
    hypervisor_hostname,
    phase,
    localAddr,
    remoteAddr,
    authScheme,
    opaque,
    event_time,
):
    """Process a graphics event asynchronously.

    This function contains the actual event processing logic for graphics events,
    moved out of the callback to allow non-blocking execution in a thread pool.

    Args:
        domain_name: The domain name
        hypervisor_hostname: The hypervisor hostname
        phase: The graphics event phase
        localAddr: Local address dict with 'node' and 'service'
        remoteAddr: Remote address dict with 'node' and 'service'
        authScheme: Authentication scheme used
        opaque: Opaque data passed to callback
        event_time: Timestamp when event was received
    """
    global lock
    global last_chain_event_graphics
    global last_timestamp_event_graphics

    try:
        with lock:
            key_domain_hyp_phase = domain_name + hypervisor_hostname + str(phase)

            if key_domain_hyp_phase not in last_timestamp_event_graphics.keys():
                last_timestamp_event_graphics[key_domain_hyp_phase] = 0.0
            if key_domain_hyp_phase not in last_chain_event_graphics.keys():
                last_chain_event_graphics[key_domain_hyp_phase] = ""

            chain_event_graphics = (
                "graphics_"
                + hypervisor_hostname
                + domain_name
                + localAddr["node"]
                + remoteAddr["node"]
            )

            diff_time = event_time - last_timestamp_event_graphics[key_domain_hyp_phase]

            logs.status.debug(
                "phase:{} - key:{} - diff:{} - now:{} - before:{}".format(
                    phase,
                    key_domain_hyp_phase,
                    diff_time,
                    event_time,
                    last_timestamp_event_graphics[key_domain_hyp_phase],
                )
            )
            logs.status.debug("chainnew: {}".format(chain_event_graphics))
            logs.status.debug(
                "chainold: {}".format(last_chain_event_graphics[key_domain_hyp_phase])
            )

            # if same event in less than 1 second, not log the event in table
            if (
                last_chain_event_graphics[key_domain_hyp_phase] == chain_event_graphics
                and diff_time < 1
            ):
                logs.status.debug(
                    "event repeated: diff_time {} - phase:{} - {}".format(
                        diff_time, str(phase), chain_event_graphics
                    )
                )

            else:
                dict_event = {
                    "domain": domain_name,
                    "hyp_hostname": hypervisor_hostname,
                    "event": "graphics_event",
                    "phase": phase,
                    "authScheme": authScheme,
                    "localAddr": localAddr["node"],
                    "localPort": localAddr["service"],
                    "remoteAddr": remoteAddr["node"],
                    "remotePort": remoteAddr["service"],
                    "chainnew": chain_event_graphics,
                    "chainold": last_chain_event_graphics[key_domain_hyp_phase],
                    "last": last_timestamp_event_graphics[key_domain_hyp_phase],
                    "diff": diff_time,
                    "when": event_time,
                }

                logs.status.debug(
                    "myDomainEventGraphicsCallback: Domain %s %s"
                    % (domain_name, authScheme)
                )
                logs.status.debug(
                    "localAddr: {},remoteAddr: {}, phase:{}".format(
                        localAddr["node"], remoteAddr["node"], phase
                    )
                )

            last_chain_event_graphics[key_domain_hyp_phase] = chain_event_graphics
            last_timestamp_event_graphics[key_domain_hyp_phase] = event_time

    except Exception as e:
        logs.status.error(f"Error processing graphics event async: {e}")
        log.error("Traceback: {}".format(traceback.format_exc()))


def myDomainEventGraphicsCallbackRethink(
    conn, dom, phase, localAddr, remoteAddr, authScheme, subject, opaque
):
    """Non-blocking graphics event callback.

    This callback extracts minimal information quickly and queues the actual
    processing work to a thread pool. This ensures the libvirt event loop
    is not blocked by slow operations.
    """
    # Extract info quickly - these are fast libvirt calls
    now = int(time.time())
    domain_name = dom.name()
    hypervisor_hostname = conn.getHostname()

    # Copy the address dicts since they may not be valid after callback returns
    local_addr_copy = {"node": localAddr["node"], "service": localAddr["service"]}
    remote_addr_copy = {"node": remoteAddr["node"], "service": remoteAddr["service"]}

    # Queue the actual processing to the thread pool
    _event_processor_pool.submit(
        _process_graphics_event_async,
        domain_name,
        hypervisor_hostname,
        phase,
        local_addr_copy,
        remote_addr_copy,
        authScheme,
        opaque,
        now,
    )


r_status = RethinkHypEvent()


class ThreadHypEvents(threading.Thread):
    def __init__(self, name, register_graphics_events=True):
        threading.Thread.__init__(self)
        self.name = name
        self.stop = False
        self.stop_event_loop = [False]
        self.REGISTER_GRAPHICS_EVENTS = register_graphics_events
        self.hyps = {}
        # self.hostname = get_hyp_hostname_from_id(hyp_id)
        self.hyps_conn = dict()
        self.hyps_workers = dict()
        self.events_ids = dict()
        self.q_event_register = PriorityQueueIsard()

    def run(self):
        # Close connection on exit (to test cleanup paths)
        self.tid = get_tid()
        logs.status.info("starting thread: {} (TID {})".format(self.name, self.tid))
        old_exitfunc = getattr(sys, "exitfunc", None)

        def exit():
            logs.status.info("Closing hypervisors connexions")
            for hyp_id, hostname in self.hyps.items():
                self.hyps_conn[hyp_id].close()
            if old_exitfunc:
                old_exitfunc()

        sys.exitfunc = exit

        self.thread_event_loop = virEventLoopNativeStart(self.stop_event_loop)

        # self.r_status = RethinkHypEvent()
        while self.stop is not True:
            try:
                action = self.q_event_register.get(
                    timeout=TIMEOUT_QUEUE_REGISTER_EVENTS
                )
                if action["type"] in ["add_hyp_to_receive_events"]:
                    hyp_id = action["hyp_id"]
                    self.add_hyp_to_receive_events(hyp_id, action["worker"])
                elif action["type"] in ["del_hyp_to_receive_events"]:
                    hyp_id = action["hyp_id"]
                    self.del_hyp_to_receive_events(hyp_id)
                elif action["type"] == "stop_thread":
                    self.stop = True
                else:
                    logs.status.error(
                        "type action {} not supported".format(action["type"])
                    )
            except queue.Empty:
                pass
            except Exception as e:
                logs.exception_id.debug("0006")
                log.error("Exception in ThreadHypEvents main loop: {}".format(e))
                log.error("Action: {}".format(pprint.pformat(action)))
                log.error("Traceback: {}".format(traceback.format_exc()))
                return False

        self.stop_event_loop[0] = True
        while self.thread_event_loop.is_alive():
            pass

    def add_hyp_to_receive_events(self, hyp_id, worker):
        print("add_hyp_to_receive_events")
        d_hyp_parameters = get_hyp_hostname_user_port_from_id(hyp_id)
        hostname = d_hyp_parameters["hostname"]
        user = d_hyp_parameters.get("user", "root")
        port = d_hyp_parameters.get("port", 22)

        uri = hostname_to_uri(hostname, user=user, port=port)
        conn_ok = False
        try:
            self.hyps_conn[hyp_id] = libvirt.openReadOnly(uri)
            self.hyps_workers[hyp_id] = worker
            logs.status.info(
                "####################connection to {} ready in events thread".format(
                    hyp_id
                )
            )
            update_uri_hyp(hyp_id, uri)
            conn_ok = True
        except Exception as e:
            logs.exception_id.debug("0007")
            logs.status.error(
                "libvirt connection read only in events thread in hypervisor: {}".format(
                    hyp_id
                )
            )
            logs.status.error(e)

        if conn_ok is True:
            for i in range(NUM_TRY_REGISTER_EVENTS):
                # try 5
                try:
                    self.events_ids[hyp_id] = self.register_events(
                        self.hyps_conn[hyp_id]
                    )
                    self.hyps[hyp_id] = hostname
                    break
                except libvirt.libvirtError as e:
                    logs.status.error(
                        f"Error when register_events, wait {SLEEP_BETWEEN_TRY_REGISTER_EVENTS}, try {i+1} of {NUM_TRY_REGISTER_EVENTS}"
                    )
                    logs.status.error(e)
                time.sleep(SLEEP_BETWEEN_TRY_REGISTER_EVENTS)

    def del_hyp_to_receive_events(self, hyp_id):
        if hyp_id in self.hyps_conn.keys():
            try:
                self.unregister_events(self.hyps_conn[hyp_id], self.events_ids[hyp_id])
            except Exception as e:
                logs.exception_id.debug("0008")
                logs.status.error(
                    f"Error unregistering event in hypervisor {hyp_id}. Exception: {e}"
                )
            try:
                self.hyps_conn[hyp_id].close()
            except Exception as e:
                logs.exception_id.debug("0009")
                logs.status.error(
                    "Error closing libvirt connection. libvirt connection events in read only can not be closed?: {}".format(
                        hyp_id
                    )
                )
                logs.status.error(e)

            self.hyps_conn.pop(hyp_id)
            self.events_ids.pop(hyp_id)
            self.hyps.pop(hyp_id)

    def register_events(self, hyp_libvirt_conn):
        # r_status = self.r_status
        global r_status
        cb_ids = {}

        hyp_libvirt_conn.registerCloseCallback(myConnectionCloseCallback, None)

        cb_ids["VIR_DOMAIN_EVENT_ID_LIFECYCLE"] = (
            hyp_libvirt_conn.domainEventRegisterAny(
                None,
                libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE,
                myDomainEventCallbackRethink,
                r_status,
            )
        )
        # hyp_libvirt_conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_REBOOT, myDomainEventRebootCallback, None)

        #######################################
        # IF YOU WANT TO REGISTER IN LOGS IO ERRORS UNCOMMENT THIS LINES
        #  if one domain have io errors temporally logs grows and have lot of messages
        #  by default we prefer disable this event handler
        #
        #        cb_ids['VIR_DOMAIN_EVENT_ID_IO_ERROR'] = hyp_libvirt_conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_IO_ERROR, myDomainEventIOErrorCallback, None)

        #        cb_ids['VIR_DOMAIN_EVENT_ID_IO_ERROR_REASON'] = hyp_libvirt_conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_IO_ERROR_REASON, myDomainEventIOErrorReasonCallback, None)

        #
        ########################################

        # INFO TO DEVELOPER: by default registering graphics events
        if self.REGISTER_GRAPHICS_EVENTS:
            cb_ids["VIR_DOMAIN_EVENT_ID_GRAPHICS"] = (
                hyp_libvirt_conn.domainEventRegisterAny(
                    None,
                    libvirt.VIR_DOMAIN_EVENT_ID_GRAPHICS,
                    myDomainEventGraphicsCallbackRethink,
                    r_status,
                )
            )

        cb_ids["VIR_DOMAIN_EVENT_ID_CONTROL_ERROR"] = (
            hyp_libvirt_conn.domainEventRegisterAny(
                None,
                libvirt.VIR_DOMAIN_EVENT_ID_CONTROL_ERROR,
                myDomainEventControlErrorCallback,
                None,
            )
        )
        # hyp_libvirt_conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_BLOCK_JOB, myDomainEventBlockJobCallback, None)
        # hyp_libvirt_conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_BALLOON_CHANGE, myDomainEventBalloonChangeCallback, None)
        # hyp_libvirt_conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_DEVICE_REMOVED, myDomainEventDeviceRemovedCallback, None)
        # hyp_libvirt_conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_TUNABLE, myDomainEventTunableCallback, None)
        # hyp_libvirt_conn.networkEventRegisterAny(None, libvirt.VIR_NETWORK_EVENT_ID_LIFECYCLE, myNetworkEventLifecycleCallback, None)

        # QEMU Guest Agent
        def myDomainEventAgentLifecycleCallback(conn, dom, state, reason, opaque):
            # TODO: RethinkDB
            logs.status.info(
                "myDomainEventAgentLifecycleCallback: Domain %s(%s) %s %s"
                % (
                    dom.name(),
                    dom.ID(),
                    agentLifecycleStateToString(state),
                    agentLifecycleReasonToString(reason),
                )
            )

            if (
                state
                == libvirt.VIR_CONNECT_DOMAIN_EVENT_AGENT_LIFECYCLE_STATE_CONNECTED
            ):
                hyp_id = get_id_hyp_from_uri(conn.getURI())
                desktop_id = dom.name()
                self.hyps_workers[hyp_id].queue_actions.put(
                    {"type": "personal_unit", "desktop_id": desktop_id},
                    Q_PRIORITY_PERSONAL_UNIT,
                )
                logs.main.info(f"Personal unit mount of {desktop_id} queued")

        cb_ids["VIR_DOMAIN_EVENT_ID_AGENT_LIFECYCLE"] = (
            hyp_libvirt_conn.domainEventRegisterAny(
                None,
                libvirt.VIR_DOMAIN_EVENT_ID_AGENT_LIFECYCLE,
                myDomainEventAgentLifecycleCallback,
                None,
            )
        )

        hyp_libvirt_conn.setKeepAlive(5, 3)
        return cb_ids

    def unregister_events(self, hyp_libvirt_conn, cb_ids):
        # deregister
        for k in list(cb_ids.keys()):
            hyp_libvirt_conn.domainEventDeregisterAny(cb_ids[k])

        hyp_libvirt_conn.unregisterCloseCallback()


def launch_thread_hyps_event():
    # t = threading.Thread(name= 'events',target=events_from_hyps, args=[list_hostnames])

    t = ThreadHypEvents(name="hyps_events")
    t.daemon = True
    t.start()
    return t
