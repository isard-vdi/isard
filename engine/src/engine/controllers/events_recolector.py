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
from engine.services.lib.libvirt_timeout import (
    execute_with_timeout,
    submit_libvirt_call,
    unregister_hypervisor_executor,
)
from engine.services.log import *

TIMEOUT_QUEUE_REGISTER_EVENTS = 1
EVENTS_SUBSCRIBE_TIMEOUT = 30
EVENTS_RETIRE_TIMEOUT = 10

# repeats for ever: nothing else rearms an Online hypervisor whose subscription failed
SUBSCRIBE_RETRY_BACKOFF = (5, 15, 30, 60, 120, 300)

SUBSCRIPTION_DOWN_REPORT_SECONDS = 60

# not the bare hyp_id key: that single-thread executor is the worker's, busy with createXML
EVENTS_EXECUTOR_PREFIX = "evrec:"

# In the order libvirt numbers them (VIR_CONNECT_CLOSE_REASON_*).
CONNECTION_CLOSE_REASONS = (
    "Error",
    "End-of-file",
    "Keepalive",
    "Client",
)

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
    """libvirt dropped one of our connections; runs on its dispatch thread, so never raise or block."""
    hyp_id = None
    try:
        thread, hyp_id = opaque if opaque else (None, None)
        why = (
            CONNECTION_CLOSE_REASONS[reason]
            if isinstance(reason, int) and 0 <= reason < len(CONNECTION_CLOSE_REASONS)
            else "reason_{}".format(reason)
        )
        if thread is None or hyp_id is None:
            return
        # by identity, not reason: libvirt also reports Client for subscriptions we did not retire
        if thread.hyps_conn.get(hyp_id) is not conn:
            logs.status.info(
                "EVREC_CONN_LOST_STALE hyp={} reason={} - already retired".format(
                    hyp_id, why
                )
            )
            return
        delay = thread.schedule_subscription(hyp_id, "close callback: {}".format(why))
        logs.status.warning(
            "EVREC_CONN_LOST hyp={} reason={} retry_in={}s - this hypervisor "
            "receives NO libvirt events until it is back".format(hyp_id, why, delay)
        )
    except Exception as e:
        logs.status.error(
            "EVREC_CONN_LOST_UNHANDLED hyp={} error={}".format(hyp_id or "?", e)
        )


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
        self.thread_event_loop = None
        # written from libvirt's dispatch thread too; the lock also guards the dicts above
        self._pending = dict()
        self._inflight = dict()
        self._lock = threading.RLock()
        self._last_down_report = 0.0

    def run(self):
        self.tid = get_tid()
        logs.status.info("starting thread: {} (TID {})".format(self.name, self.tid))

        self.thread_event_loop = virEventLoopNativeStart(self.stop_event_loop)

        try:
            while self.stop is not True:
                # bound before the get: the error handler formats it
                action = None
                try:
                    action = self.q_event_register.get(
                        timeout=TIMEOUT_QUEUE_REGISTER_EVENTS
                    )
                except queue.Empty:
                    action = None
                except Exception as e:
                    logs.status.error(
                        "EVREC_QUEUE_ERROR error={} - loop continues".format(e)
                    )
                    action = None

                if action is not None:
                    self._dispatch(action)
                if self.stop is not True:
                    self._service_subscriptions()
        except (SystemExit, KeyboardInterrupt):
            self.stop = True
            raise
        finally:
            self._shutdown()

    def _shutdown(self):
        if self.stop is True:
            self.stop_event_loop[0] = True
            deadline = time.time() + 10
            while (
                self.thread_event_loop is not None
                and self.thread_event_loop.is_alive()
                and time.time() < deadline
            ):
                time.sleep(0.05)
            logs.status.info(
                "EVREC_THREAD_EXIT reason=stop_requested subscribed={}".format(
                    sorted(self.hyps_conn)
                )
            )
        else:
            # keep the native loop: losing delivery fleet-wide is worse than losing registration
            logs.status.error(
                "EVREC_THREAD_EXIT reason=unhandled subscribed={} - libvirt "
                "events are still being delivered but NO hypervisor can be "
                "added or removed until the engine restarts".format(
                    sorted(self.hyps_conn)
                )
            )

    def _dispatch(self, action):
        """One queued action, and it can never take the thread with it."""
        action_type = None
        hyp_id = None
        try:
            action_type = action["type"]
            hyp_id = action.get("hyp_id")
            if action_type == "add_hyp_to_receive_events":
                self.add_hyp_to_receive_events(hyp_id, action.get("worker"))
            elif action_type == "del_hyp_to_receive_events":
                self.del_hyp_to_receive_events(hyp_id)
            elif action_type == "stop_thread":
                self.stop = True
            else:
                logs.status.error("type action {} not supported".format(action_type))
        except Exception as e:
            logs.exception_id.debug("0006")
            logs.status.error(
                "EVREC_ACTION_FAILED type={} hyp={} error={} - loop "
                "continues".format(action_type, hyp_id, e)
            )
            log.error("Action: {}".format(pprint.pformat(action)))
            log.error("Traceback: {}".format(traceback.format_exc()))
            if hyp_id and action_type == "add_hyp_to_receive_events":
                # or the hypervisor would silently lose its subscription for ever
                self.schedule_subscription(hyp_id, "action failed: {}".format(e))

    def schedule_subscription(self, hyp_id, reason):
        """Owe this hypervisor a (re)subscription and return the delay; q_event_register is single-producer."""
        now = time.time()
        with self._lock:
            pending = self._pending.get(hyp_id)
            failures = (pending["failures"] + 1) if pending else 1
            delay = SUBSCRIBE_RETRY_BACKOFF[
                min(failures - 1, len(SUBSCRIBE_RETRY_BACKOFF) - 1)
            ]
            self._pending[hyp_id] = {
                "failures": failures,
                "down_since": pending["down_since"] if pending else now,
                "next_try": now + delay,
                "reason": reason,
            }
        return delay

    def forget_subscription(self, hyp_id):
        with self._lock:
            self._pending.pop(hyp_id, None)

    def _service_subscriptions(self):
        """One tick of the subscription clock. Never blocks on libvirt."""
        self._collect_in_flight()
        self._start_one_due_subscription()
        self._report_subscriptions_down()

    def _start_one_due_subscription(self):
        now = time.time()
        with self._lock:
            due = sorted(
                (p["next_try"], h)
                for h, p in self._pending.items()
                if p["next_try"] <= now and h not in self._inflight
            )
        for _, hyp_id in due:
            if hyp_id not in self.hyps_workers:
                # A deregistration got here first: the only stop clause there is.
                self.forget_subscription(hyp_id)
                continue
            try:
                self.add_hyp_to_receive_events(hyp_id, self.hyps_workers.get(hyp_id))
            except Exception as e:
                self.schedule_subscription(hyp_id, "retry raised: {}".format(e))
                logs.status.error(
                    "EVREC_SUBSCRIBE_FAILED hyp={} phase=retry error={}".format(
                        hyp_id, e
                    )
                )
            # one per pass, so a fleet-wide outage cannot starve registration and deregistration
            return

    def _report_subscriptions_down(self):
        now = time.time()
        with self._lock:
            down = {h: dict(p) for h, p in self._pending.items()}
        if not down:
            # Reset so the next outage is reported the moment it starts.
            self._last_down_report = 0.0
            return
        if now - self._last_down_report < SUBSCRIPTION_DOWN_REPORT_SECONDS:
            return
        self._last_down_report = now
        logs.status.error(
            "EVREC_SUBSCRIPTION_DOWN count={} hyps={} oldest_s={} - receiving "
            "no libvirt events".format(
                len(down),
                ",".join(sorted(down)),
                int(now - min(p["down_since"] for p in down.values())),
            )
        )

    def add_hyp_to_receive_events(self, hyp_id, worker=None):
        """Build or rebuild the subscription without blocking; the old one stays until its replacement registers."""
        if not hyp_id:
            logs.status.error("EVREC_SUBSCRIBE_NO_HYP action carried no hyp_id")
            return False
        if worker is not None:
            self.hyps_workers[hyp_id] = worker
        if hyp_id in self._inflight:
            logs.status.info(
                "EVREC_SUBSCRIBE_IN_FLIGHT hyp={} - an attempt is already "
                "running, not starting a second one".format(hyp_id)
            )
            return False

        try:
            d_hyp_parameters = get_hyp_hostname_user_port_from_id(hyp_id)
        except Exception as e:
            delay = self.schedule_subscription(hyp_id, "lookup raised: {}".format(e))
            logs.status.error(
                "EVREC_SUBSCRIBE_FAILED hyp={} phase=lookup retry_in={}s "
                "error={}".format(hyp_id, delay, e)
            )
            return False

        if not d_hyp_parameters or not d_hyp_parameters.get("hostname"):
            # Row gone: the one place where giving up is the right answer.
            self.forget_subscription(hyp_id)
            logs.status.error(
                "EVREC_SUBSCRIBE_ABANDONED hyp={} phase=lookup reason=no_row - "
                "no hostname/user/port in the database, not retrying".format(hyp_id)
            )
            return False

        hostname = d_hyp_parameters["hostname"]
        user = d_hyp_parameters.get("user", "root")
        port = d_hyp_parameters.get("port", 22)
        uri = hostname_to_uri(hostname, user=user, port=port)

        try:
            # before subscribing: get_id_hyp_from_uri drops events whose uri it cannot map
            update_uri_hyp(hyp_id, uri)
        except Exception as e:
            logs.status.warning(
                "EVREC_URI_WRITE_FAILED hyp={} uri={} error={}".format(hyp_id, uri, e)
            )

        try:
            future = submit_libvirt_call(
                self._open_and_register,
                args=(uri, hyp_id),
                operation_name="events.subscribe",
                hyp_id=EVENTS_EXECUTOR_PREFIX + hyp_id,
            )
        except Exception as e:
            delay = self.schedule_subscription(hyp_id, "submit failed: {}".format(e))
            logs.status.error(
                "EVREC_SUBSCRIBE_FAILED hyp={} phase=submit retry_in={}s "
                "error={}".format(hyp_id, delay, e)
            )
            return False

        self._inflight[hyp_id] = {
            "future": future,
            "uri": uri,
            "hostname": hostname,
            "deadline": time.time() + EVENTS_SUBSCRIBE_TIMEOUT,
        }
        return True

    def _open_and_register(self, uri, hyp_id):
        """Open a read-only connection and subscribe on it, off the loop."""
        conn = libvirt.openReadOnly(uri)
        if conn is None:
            raise libvirt.libvirtError("openReadOnly returned None for {}".format(uri))
        try:
            return conn, self.register_events(conn, hyp_id)
        except Exception:
            # libvirt refuses a second close callback, so a half-registered connection is discarded
            try:
                conn.close()
            except Exception:
                pass
            raise

    def _collect_in_flight(self):
        now = time.time()
        for hyp_id, job in list(self._inflight.items()):
            future = job["future"]
            if not future.done():
                if now < job["deadline"]:
                    continue
                self._inflight.pop(hyp_id, None)
                # abandoned, not cancelled: the call cannot be killed, so its executor is dropped too
                self._dispose_when_done(future)
                self._drop_executor(hyp_id)
                delay = self.schedule_subscription(hyp_id, "open timed out")
                logs.status.error(
                    "EVREC_SUBSCRIBE_FAILED hyp={} phase=open uri={} "
                    "timeout={}s retry_in={}s previous_subscription={}".format(
                        hyp_id,
                        job["uri"],
                        EVENTS_SUBSCRIBE_TIMEOUT,
                        delay,
                        "kept" if hyp_id in self.hyps_conn else "none",
                    )
                )
                continue

            self._inflight.pop(hyp_id, None)
            try:
                conn, cb_ids = future.result()
            except Exception as e:
                logs.exception_id.debug("0007")
                delay = self.schedule_subscription(hyp_id, "subscribe: {}".format(e))
                logs.status.error(
                    "EVREC_SUBSCRIBE_FAILED hyp={} phase=open uri={} "
                    "retry_in={}s previous_subscription={} error={}".format(
                        hyp_id,
                        job["uri"],
                        delay,
                        "kept" if hyp_id in self.hyps_conn else "none",
                        e,
                    )
                )
                continue
            self._install_subscription(hyp_id, job, conn, cb_ids)

    def _install_subscription(self, hyp_id, job, conn, cb_ids):
        """Retire the old subscription only once the new one is registered."""
        if hyp_id not in self.hyps_workers:
            # A del_ arrived while the handshake was in flight.
            self.forget_subscription(hyp_id)
            self._retire(hyp_id, conn, cb_ids, "deregistered while opening")
            return

        with self._lock:
            pending = self._pending.pop(hyp_id, None)
            old_conn = self.hyps_conn.get(hyp_id)
            old_ids = self.events_ids.get(hyp_id)
            self.hyps_conn[hyp_id] = conn
            self.events_ids[hyp_id] = cb_ids
            self.hyps[hyp_id] = job["hostname"]

        if old_conn is not None and old_conn is not conn:
            self._retire(hyp_id, old_conn, old_ids, "replaced")

        logs.status.info(
            "####################connection to {} ready in events thread".format(hyp_id)
        )
        logs.status.info(
            "EVREC_SUBSCRIBED hyp={} uri={} callbacks={} replaced={} "
            "down_for={}s attempts={}".format(
                hyp_id,
                job["uri"],
                len(cb_ids),
                int(old_conn is not None),
                int(time.time() - pending["down_since"]) if pending else 0,
                pending["failures"] if pending else 0,
            )
        )
        return True

    def del_hyp_to_receive_events(self, hyp_id):
        """Forget a hypervisor. Symmetric with add, and it cannot raise."""
        if not hyp_id:
            logs.status.error("EVREC_UNSUBSCRIBE_NO_HYP action carried no hyp_id")
            return
        with self._lock:
            conn = self.hyps_conn.pop(hyp_id, None)
            cb_ids = self.events_ids.pop(hyp_id, None)
            self.hyps.pop(hyp_id, None)
            self._pending.pop(hyp_id, None)
        job = self._inflight.pop(hyp_id, None)
        if job is not None:
            self._dispose_when_done(job["future"])

        if conn is not None:
            self._retire(hyp_id, conn, cb_ids, "deregistered")

        # after the retire: until then the connection delivers and the agent callback reads it
        self.hyps_workers.pop(hyp_id, None)
        self._drop_executor(hyp_id)
        logs.status.info(
            "EVREC_UNSUBSCRIBED hyp={} had_subscription={}".format(
                hyp_id, int(conn is not None)
            )
        )

    def _retire(self, hyp_id, conn, cb_ids, why):
        """Deregister and close a connection; blocks the loop up to EVENTS_RETIRE_TIMEOUT."""
        try:
            problems = execute_with_timeout(
                self._retire_calls,
                args=(conn, cb_ids or {}),
                timeout=EVENTS_RETIRE_TIMEOUT,
                operation_name="events.retire",
                hyp_id=EVENTS_EXECUTOR_PREFIX + hyp_id,
            )
        except Exception as e:
            logs.exception_id.debug("0008")
            logs.status.warning(
                "EVREC_RETIRE_FAILED hyp={} why={} error={} - it is out of the "
                "collector's dictionaries either way".format(hyp_id, why, e)
            )
            return
        if problems:
            # expected when the connection being retired is the one that died
            logs.status.warning(
                "EVREC_RETIRE_PARTIAL hyp={} why={} problems={}".format(
                    hyp_id, why, problems
                )
            )

    def _retire_calls(self, conn, cb_ids):
        problems = self.unregister_events(conn, cb_ids)
        try:
            conn.close()
        except Exception as e:
            logs.exception_id.debug("0009")
            problems = list(problems) + ["close: {}".format(e)]
        return problems

    def _dispose_when_done(self, future):
        """Close a connection we stopped waiting for, if it ever arrives."""

        def _dispose(f):
            try:
                conn, _ = f.result()
            except Exception:
                return
            try:
                conn.close()
            except Exception:
                pass

        try:
            future.add_done_callback(_dispose)
        except Exception:
            pass

    def _drop_executor(self, hyp_id):
        try:
            unregister_hypervisor_executor(EVENTS_EXECUTOR_PREFIX + hyp_id)
        except Exception as e:
            logs.status.warning(
                "EVREC_EXECUTOR_CLEANUP_FAILED hyp={} error={}".format(hyp_id, e)
            )

    def subscription_report(self):
        """Per hypervisor, whether events are delivered: a held connection with no rebuild owed."""
        with self._lock:
            pending = {h: dict(p) for h, p in self._pending.items()}
            conns = set(self.hyps_conn)
            opening = set(self._inflight)
        down = set(pending) | (opening - conns)
        now = time.time()
        detail = {}
        for hyp_id in down:
            p = pending.get(hyp_id)
            detail[hyp_id] = {
                "failures": p["failures"] if p else 0,
                "down_for": int(now - p["down_since"]) if p else 0,
                "next_try_in": max(0, int(p["next_try"] - now)) if p else 0,
                "reason": p["reason"] if p else "opening",
            }
        return {
            "thread_alive": self.is_alive(),
            "event_loop_alive": bool(
                self.thread_event_loop is not None and self.thread_event_loop.is_alive()
            ),
            "subscribed": sorted(conns - down),
            "events_down": sorted(down),
            "detail": detail,
        }

    def register_events(self, hyp_libvirt_conn, hyp_id=None):
        # r_status = self.r_status
        global r_status
        cb_ids = {}

        # first, so every RPC below has a deadline; a refusal does not refuse the subscription
        try:
            hyp_libvirt_conn.setKeepAlive(5, 3)
        except Exception as e:
            logs.status.warning(
                "EVREC_KEEPALIVE_REFUSED hyp={} error={} - RPCs on this "
                "connection are unbounded".format(hyp_id, e)
            )

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
                agent_hyp_id = get_id_hyp_from_uri(conn.getURI())
                desktop_id = dom.name()
                worker = self.hyps_workers.get(agent_hyp_id)
                if worker is None:
                    # on libvirt's dispatch thread nothing of ours would catch a KeyError
                    logs.status.warning(
                        "EVREC_AGENT_NO_WORKER hyp={} desktop={} - personal "
                        "unit not queued".format(agent_hyp_id, desktop_id)
                    )
                    return
                worker.queue_actions.put(
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

        # last: libvirt refuses a second close callback, so registering it earlier blocks retries
        hyp_libvirt_conn.registerCloseCallback(
            myConnectionCloseCallback, (self, hyp_id)
        )
        return cb_ids

    def unregister_events(self, hyp_libvirt_conn, cb_ids):
        """Deregister everything, and report rather than abort."""
        problems = []
        for k in list((cb_ids or {}).keys()):
            try:
                hyp_libvirt_conn.domainEventDeregisterAny(cb_ids[k])
            except Exception as e:
                problems.append("{}: {}".format(k, e))
        try:
            hyp_libvirt_conn.unregisterCloseCallback()
        except Exception as e:
            problems.append("closeCallback: {}".format(e))
        return problems


def launch_thread_hyps_event():
    # t = threading.Thread(name= 'events',target=events_from_hyps, args=[list_hostnames])

    t = ThreadHypEvents(name="hyps_events")
    t.daemon = True
    t.start()
    return t
