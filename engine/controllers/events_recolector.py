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

import sys
import threading
import time

import libvirt

from engine.models.domain_xml import DomainXML
from engine.models.rethink_hyp_event import RethinkHypEvent
from engine.services.db import update_domain_viewer_started_values, get_domain_hyp_started_and_status_and_detail, \
    remove_domain_viewer_values, get_domain, get_domain_status, update_domain_status, get_id_hyp_from_uri, \
    update_uri_hyp, get_hyp_hostname_user_port_from_id
from engine.services.lib.functions import hostname_to_uri, get_tid
from engine.services.log import *


def virEventLoopNativeRun():
    while True:
        libvirt.virEventRunDefaultImpl()


# Spawn a background thread to run the event loop
def virEventLoopPureStart():
    #    global eventLoopThread
    virEventLoopPureRegister()
    eventLoopThread = threading.Thread(target=virEventLoopPureRun, name="libvirtEventLoop")
    eventLoopThread.setDaemon(True)
    eventLoopThread.start()


# def virEventLoopNativeStart(hostname='unknowhost'):
#     global eventLoopThread
#     libvirt.virEventRegisterDefaultImpl()
#     eventLoopThread = threading.Thread(target=virEventLoopNativeRun, name="EventLoop_{}".format(hostname))
#     eventLoopThread.setDaemon(True)
#     eventLoopThread.start()
#
def virEventLoopNativeStart():
    libvirt.virEventRegisterDefaultImpl()
    eventLoopThread = threading.Thread(target=virEventLoopNativeRun, name="EventLoop")
    eventLoopThread.setDaemon(True)
    eventLoopThread.start()
    return eventLoopThread


##########################################################################
# Everything that now follows is a simple demo of domain lifecycle events
##########################################################################

def domEventToString(event):
    domEventStrings = ("Defined",
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
    domEventStrings = (
        ("Added", "Updated"),
        ("Removed",),
        ("Booted", "Migrated", "Restored", "Snapshot", "Wakeup"),
        ("Paused", "Migrated", "IOError", "Watchdog", "Restored", "Snapshot", "API error"),
        ("Unpaused", "Migrated", "Snapshot"),
        ("Shutdown", "Destroyed", "Crashed", "Migrated", "Saved", "Failed", "Snapshot"),
        ("Finished",),
        ("Memory", "Disk"),
        ("Panicked",),
    )
    return domEventStrings[event][detail]


def blockJobTypeToString(type):
    blockJobTypes = ("unknown", "Pull", "Copy", "Commit", "ActiveCommit",)
    return blockJobTypes[type]


def blockJobStatusToString(status):
    blockJobStatus = ("Completed", "Failed", "Canceled", "Ready",)
    return blockJobStatus[status]


def agentLifecycleStateToString(state):
    agentStates = ("unknown", "connected", "disconnected",)
    return agentStates[state]


def agentLifecycleReasonToString(reason):
    agentReasons = ("unknown", "domain started", "channel event",)
    return agentReasons[reason]


def myDomainEventCallback1(conn, dom, event, detail, opaque):
    log.debug("myDomainEventCallback1 EVENT: Domain %s(%s) %s %s" % (dom.name(), dom.ID(),
                                                                     domEventToString(event),
                                                                     domDetailToString(event, detail)))


def myDomainEventGraphicsCallback(conn, dom, phase, localAddr, remoteAddr, authScheme, subject, opaque):
    log.debug("myDomainEventGraphicsCallback: Domain %s(%s) %d %s" % (dom.name(), dom.ID(), phase, authScheme))
    # log.debug("localAddr: {},remoteAddr: {}, phase:{}, subject:{}" % (localAddr, remoteAddr, phase, str(type(subject))))


def myDomainEventRebootCallback(conn, dom, opaque):
    log.debug("myDomainEventRebootCallback: Domain %s(%s)" % (dom.name(), dom.ID()))


def myDomainEventRTCChangeCallback(conn, dom, utcoffset, opaque):
    log.debug("myDomainEventRTCChangeCallback: Domain %s(%s) %d" % (dom.name(), dom.ID(), utcoffset))


def myDomainEventWatchdogCallback(conn, dom, action, opaque):
    log.debug("myDomainEventWatchdogCallback: Domain %s(%s) %d" % (dom.name(), dom.ID(), action))


def myDomainEventIOErrorCallback(conn, dom, srcpath, devalias, action, opaque):
    log.error(
        "myDomainEventIOErrorCallback: Domain %s(%s) %s %s %d" % (dom.name(), dom.ID(), srcpath, devalias, action))


def myDomainEventIOErrorReasonCallback(conn, dom, srcpath, devalias, action, reason, opaque):
    log.debug("myDomainEventIOErrorReasonCallback: Domain %s(%s) %s %s %d %s" % (
        dom.name(), dom.ID(), srcpath, devalias, action, reason))


def myDomainEventControlErrorCallback(conn, dom, opaque):
    log.debug("myDomainEventControlErrorCallback: Domain %s(%s)" % (dom.name(), dom.ID()))


def myDomainEventBlockJobCallback(conn, dom, disk, type, status, opaque):
    log.debug("myDomainEventBlockJobCallback: Domain %s(%s) %s on disk %s %s" % (
        dom.name(), dom.ID(), blockJobTypeToString(type), disk, blockJobStatusToString(status)))


def myDomainEventDiskChangeCallback(conn, dom, oldSrcPath, newSrcPath, devAlias, reason, opaque):
    log.debug(
        "myDomainEventDiskChangeCallback: Domain %s(%s) disk change oldSrcPath: %s newSrcPath: %s devAlias: %s reason: %s" % (
            dom.name(), dom.ID(), oldSrcPath, newSrcPath, devAlias, reason))


def myDomainEventTrayChangeCallback(conn, dom, devAlias, reason, opaque):
    log.debug("myDomainEventTrayChangeCallback: Domain %s(%s) tray change devAlias: %s reason: %s" % (
        dom.name(), dom.ID(), devAlias, reason))


def myDomainEventPMWakeupCallback(conn, dom, reason, opaque):
    log.debug("myDomainEventPMWakeupCallback: Domain %s(%s) system pmwakeup" % (
        dom.name(), dom.ID()))


def myDomainEventPMSuspendCallback(conn, dom, reason, opaque):
    log.debug("myDomainEventPMSuspendCallback: Domain %s(%s) system pmsuspend" % (
        dom.name(), dom.ID()))


def myDomainEventBalloonChangeCallback(conn, dom, actual, opaque):
    log.debug("myDomainEventBalloonChangeCallback: Domain %s(%s) %d" % (dom.name(), dom.ID(), actual))


def myDomainEventPMSuspendDiskCallback(conn, dom, reason, opaque):
    log.debug("myDomainEventPMSuspendDiskCallback: Domain %s(%s) system pmsuspend_disk" % (
        dom.name(), dom.ID()))


def myDomainEventDeviceRemovedCallback(conn, dom, dev, opaque):
    log.debug("myDomainEventDeviceRemovedCallback: Domain %s(%s) device removed: %s" % (
        dom.name(), dom.ID(), dev))


def myDomainEventBlockJob2Callback(conn, dom, disk, type, status, opaque):
    log.debug("myDomainEventBlockJob2Callback: Domain %s(%s) %s on disk %s %s" % (
        dom.name(), dom.ID(), blockJobTypeToString(type), disk, blockJobStatusToString(status)))


def myDomainEventTunableCallback(conn, dom, params, opaque):
    log.debug("myDomainEventTunableCallback: Domain %s(%s) %s" % (dom.name(), dom.ID(), params))


def myDomainEventAgentLifecycleCallback(conn, dom, state, reason, opaque):
    log.debug("myDomainEventAgentLifecycleCallback: Domain %s(%s) %s %s" % (
        dom.name(), dom.ID(), agentLifecycleStateToString(state), agentLifecycleReasonToString(reason)))


def myDomainEventDeviceAddedCallback(conn, dom, dev, opaque):
    log.debug("myDomainEventDeviceAddedCallback: Domain %s(%s) device added: %s" % (
        dom.name(), dom.ID(), dev))


def myDomainEventMigrationIteration(conn, dom, iteration, opaque):
    log.debug("myDomainEventMigrationIteration: Domain %s(%s) started migration iteration %d" % (
        dom.name(), dom.ID(), iteration))


##########################################################################
# Network events
##########################################################################
def netEventToString(event):
    netEventStrings = ("Defined",
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
    log.debug("myNetworkEventLifecycleCallback: Network %s %s %s" % (net.name(),
                                                                     netEventToString(event),
                                                                     netDetailToString(event, detail)))


##########################################################################
# Set up and run the program
##########################################################################

def myConnectionCloseCallback(conn, reason, opaque):
    reasonStrings = (
        "Error", "End-of-file", "Keepalive", "Client",
    )
    log.debug("myConnectionCloseCallback: %s: %s" % (conn.getURI(), reasonStrings[reason]))
    run = False


##########################################################################
# New Code for IsardLib
##########################################################################

def myDomainEventCallbackRethink(conn, dom, event, detail, opaque):
    now = time.time()
    dom_id = dom.name()
    hyp_id = get_id_hyp_from_uri(conn.getURI())
    if get_domain(dom_id) is not None:
        if hyp_id is None or hyp_id == '':
            log.debug('event in Hypervisor not in database with uri.  hyp_id:{}, uri:{}'.dom_id, conn.getURI())
        r_status = opaque
        dict_event = {'domain': dom_id,
                      'hyp_id': hyp_id,
                      'event': domEventToString(event),
                      'detail': domDetailToString(event, detail),
                      'when': now}

        if dict_event['event'] in ('Started', 'Resumed'):
            try:
                xml_started = dom.XMLDesc()
                vm = DomainXML(xml_started)
                port, tlsport = vm.get_graphics_port()
                update_domain_viewer_started_values(dom_id, hyp_id=hyp_id, port=port, tlsport=tlsport)
                log.info('DOMAIN STARTED - {} in {} (port: {} / tlsport:{})'.format(dom_id, hyp_id, port, tlsport))
            except Exception as e:
                log.debug(
                    'Domain {} has been destroyed while event started is processing, typical if try domain with starting paused and destroyed'.format(
                        dom_id))
                log.debug('Exception: ' + str(e))

        if dict_event['event'] in ('Stopped', 'Shutdown'):
            remove_domain_viewer_values(dom_id)
            if get_domain_status(dict_event['domain']) != 'Stopped':
                log.debug('event {} ({}) in hypervisor {} changes status to Stopped in domain {}'.format(
                    dict_event['event'],
                    dict_event['detail'],
                    hyp_id,
                    dict_event['domain']
                ))

                update_domain_status(status='Stopped', id_domain=dict_event['domain'], hyp_id=False,
                                     detail='Ready to Start')

        r_status.insert_event_in_db(dict_event)
        if dict_event['event'] in (
                "Defined",
                "Undefined",
                # "Started",
                # "Suspended",
                # "Resumed",
                # "Stopped",
                # "Shutdown",
                "PMSuspended",
                "Crashed"
        ):
            # INFO TO DEVELOPER, ESTOY YA NO TIENE SENTIDO,
            # PERO SI VALDRAÍ LA PENA HACER UN log.error para casos raros

            log.error('event strange, why?? event: {}, domain: {}, hyp_id: {}, detail: {}'.format(
                dict_event['event'],
                dict_event['domain'],
                hyp_id,
                dict_event['detail']
            ))
        ## Alberto: FALTA QUITAR EL HYP_ID Y LOS DATOS DE SPICE AL HACER STOP

        log.debug("myDomainEventCallback3 EVENT: Domain %s(%s) %s %s in hypervisor %s" % (dom.name(), dom.ID(),
                                                                                          domEventToString(event),
                                                                                          domDetailToString(event,
                                                                                                            detail),
                                                                                          hyp_id))

        d_status_hyp_started = get_domain_hyp_started_and_status_and_detail(dict_event['domain'])
        if 'status' in d_status_hyp_started.keys():
            if d_status_hyp_started['status'] != domEventToString(event) \
                    and domEventToString(event) in ['Started', 'Stopped', 'Suspended']:
                previous_status = get_domain_status(dom.name())
                if previous_status in ['CreatingDomain']:
                    # domain continues in the previous status

                    # update_domain_status(id_domain=dom.name(),
                    #                      status=previous_status,
                    #                      hyp_id=hyp_id,
                    #                      detail="Event received: " + domDetailToString(event, detail)
                    #                      )
                    pass
                else:
                    update_domain_status(id_domain=dom.name(),
                                         status=domEventToString(event),
                                         hyp_id=hyp_id,
                                         detail="Event received: " + domDetailToString(event, detail)
                                         )
        else:
            log.error('UNKNOWN STATUS in domain {}'.format(dict_event['domain']))
    else:
        log.info('domain {} launch event in hyervisor {}, but id_domain is not in database'.format(dom_id, hyp_id))
        log.info('event: {}; detail: {}'.format(domEventToString(event), domDetailToString(event, detail)))


last_timestamp_event_graphics = dict()
last_chain_event_graphics = dict()
lock = threading.Lock()


def myDomainEventGraphicsCallbackRethink(conn, dom, phase, localAddr, remoteAddr, authScheme, subject, opaque):
    global lock

    with lock:

        global last_chain_event_graphics
        global last_timestamp_event_graphics

        now = time.time()
        domain_name = dom.name()
        hypervisor_hostname = conn.getHostname()
        key_domain_hyp_phase = domain_name + hypervisor_hostname + str(phase)

        if key_domain_hyp_phase not in last_timestamp_event_graphics.keys():
            last_timestamp_event_graphics[key_domain_hyp_phase] = 0.0
        if key_domain_hyp_phase not in last_chain_event_graphics.keys():
            last_chain_event_graphics[key_domain_hyp_phase] = ''

        # sometimes libvirt launhcs the same event more than one time:
        # chain_event_graphics = 'graphics_' + hypervisor_hostname + domain_name + str(phase) + localAddr['node'] + remoteAddr['node']
        chain_event_graphics = 'graphics_' + hypervisor_hostname + domain_name + localAddr['node'] + remoteAddr['node']

        diff_time = now - last_timestamp_event_graphics[key_domain_hyp_phase]

        log.debug('phase:{} - key:{} - diff:{} - now:{} - before:{}'.format(phase, key_domain_hyp_phase, diff_time, now,
                                                                            last_timestamp_event_graphics[
                                                                                key_domain_hyp_phase]))
        log.debug('chainnew: {}'.format(chain_event_graphics))
        log.debug('chainold: {}'.format(last_chain_event_graphics[key_domain_hyp_phase]))

        # if same event in less than 1 second, not log the event in table
        if (last_chain_event_graphics[key_domain_hyp_phase] == chain_event_graphics and diff_time < 1):
            log.debug(
                'event repeated: diff_time {} - phase:{} - {}'.format(diff_time, str(phase), chain_event_graphics))

        else:

            dict_event = {'domain': domain_name,
                          'hyp_hostname': hypervisor_hostname,
                          'event': 'graphics_event',
                          'phase': phase,
                          'authScheme': authScheme,
                          'localAddr': localAddr['node'],
                          'localPort': localAddr['service'],
                          'remoteAddr': remoteAddr['node'],
                          'remotePort': remoteAddr['service'],
                          'chainnew': chain_event_graphics,
                          'chainold': last_chain_event_graphics[key_domain_hyp_phase],
                          'last': last_timestamp_event_graphics[key_domain_hyp_phase],
                          'diff': diff_time,
                          'when': now}

            r_status = opaque

            r_status.insert_event_in_db(dict_event)
            r_status.update_viewer_client(domain_name, phase, ip_client=remoteAddr['node'], when=now)

            log.debug("myDomainEventGraphicsCallback: Domain %s(%s) %s" % (dom.name(), dom.ID(), authScheme))
            log.debug("localAddr: {},remoteAddr: {}, phase:{}".format(localAddr['node'], remoteAddr['node'], phase))

        last_chain_event_graphics[key_domain_hyp_phase] = chain_event_graphics
        last_timestamp_event_graphics[key_domain_hyp_phase] = now


r_status = RethinkHypEvent()


class ThreadHypEvents(threading.Thread):
    def __init__(self, name,
                 dict_hyps,
                 register_graphics_events=True
                 ):
        threading.Thread.__init__(self)
        self.name = name
        self.stop = False
        self.REGISTER_GRAPHICS_EVENTS = register_graphics_events
        self.hyps = dict_hyps
        # self.hostname = get_hyp_hostname_from_id(hyp_id)
        self.hyps_conn = dict()
        self.events_ids = dict()

    def run(self):
        # Close connection on exit (to test cleanup paths)
        self.tid = get_tid()
        log.info('starting thread: {} (TID {})'.format(self.name, self.tid))
        old_exitfunc = getattr(sys, 'exitfunc', None)

        def exit():
            log.info('Closing hypervisors connexions')
            for hyp_id, hostname in self.hyps.items():
                self.hyps_conn[hyp_id].close()
            if (old_exitfunc): old_exitfunc()

        sys.exitfunc = exit

        # self.r_status = RethinkHypEvent()

        self.thread_event_loop = virEventLoopNativeStart()

        for hyp_id, hostname in self.hyps.items():
            self.add_hyp_to_receive_events(hyp_id)

        while self.stop is not True:
            time.sleep(0.1)

        if self.stop is True:
            for hyp_id in self.hyps:
                self.del_hyp_to_receive_events(hyp_id)

    def add_hyp_to_receive_events(self, hyp_id):
        d_hyp_parameters = get_hyp_hostname_user_port_from_id(hyp_id)
        hostname = d_hyp_parameters['hostname']
        user = d_hyp_parameters.get('user', 'root')
        port = d_hyp_parameters.get('port', 22)

        uri = hostname_to_uri(hostname, user=user, port=port)
        conn_ok = False
        try:
            self.hyps_conn[hyp_id] = libvirt.openReadOnly(uri)
            log.debug('####################connection to {} ready in events thread'.format(hyp_id))
            update_uri_hyp(hyp_id, uri)
            conn_ok = True
        except Exception as e:
            log.error('libvirt connection read only in events thread in hypervisor: {}'.format(hyp_id))
            log.error(e)

        if conn_ok is True:
            self.events_ids[hyp_id] = self.register_events(self.hyps_conn[hyp_id])
            self.hyps[hyp_id] = hostname

    def del_hyp_to_receive_events(self, hyp_id):
        self.unregister_events(self.hyps_conn[hyp_id], self.events_ids[hyp_id])
        try:
            self.hyps_conn[hyp_id].close()
        except Exception as e:
            log.error('libvirt connection read only can not be closed: {}'.format(hyp_id))
            log.error(e)

        self.hyps_conn.pop(hyp_id)
        self.events_ids.pop(hyp_id)
        self.hyps.pop(hyp_id)

    def register_events(self, hyp_libvirt_conn):

        # r_status = self.r_status
        global r_status
        cb_ids = {}

        hyp_libvirt_conn.registerCloseCallback(myConnectionCloseCallback, None)

        cb_ids['VIR_DOMAIN_EVENT_ID_LIFECYCLE'] = hyp_libvirt_conn.domainEventRegisterAny(None,
                                                                                          libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE,
                                                                                          myDomainEventCallbackRethink,
                                                                                          r_status)
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
            cb_ids['VIR_DOMAIN_EVENT_ID_GRAPHICS'] = hyp_libvirt_conn.domainEventRegisterAny(None,
                                                                                             libvirt.VIR_DOMAIN_EVENT_ID_GRAPHICS,
                                                                                             myDomainEventGraphicsCallbackRethink,
                                                                                             r_status)

        cb_ids['VIR_DOMAIN_EVENT_ID_CONTROL_ERROR'] = hyp_libvirt_conn.domainEventRegisterAny(None,
                                                                                              libvirt.VIR_DOMAIN_EVENT_ID_CONTROL_ERROR,
                                                                                              myDomainEventControlErrorCallback,
                                                                                              None)
        # hyp_libvirt_conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_BLOCK_JOB, myDomainEventBlockJobCallback, None)
        # hyp_libvirt_conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_BALLOON_CHANGE, myDomainEventBalloonChangeCallback, None)
        # hyp_libvirt_conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_DEVICE_REMOVED, myDomainEventDeviceRemovedCallback, None)
        # hyp_libvirt_conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_TUNABLE, myDomainEventTunableCallback, None)
        # hyp_libvirt_conn.networkEventRegisterAny(None, libvirt.VIR_NETWORK_EVENT_ID_LIFECYCLE, myNetworkEventLifecycleCallback, None)

        hyp_libvirt_conn.setKeepAlive(5, 3)
        return cb_ids

    def unregister_events(self, hyp_libvirt_conn, cb_ids):

        # deregister
        hyp_libvirt_conn.domainEventDeregisterAny(self, cb_ids['VIR_DOMAIN_EVENT_ID_LIFECYCLE'])
        hyp_libvirt_conn.domainEventDeregisterAny(self, cb_ids['VIR_DOMAIN_EVENT_ID_IO_ERROR'])
        hyp_libvirt_conn.domainEventDeregisterAny(self, cb_ids['VIR_DOMAIN_EVENT_ID_GRAPHICS'])
        hyp_libvirt_conn.domainEventDeregisterAny(self, cb_ids['VIR_DOMAIN_EVENT_ID_IO_ERROR_REASON'])
        hyp_libvirt_conn.domainEventDeregisterAny(self, cb_ids['VIR_DOMAIN_EVENT_ID_CONTROL_ERROR'])

        hyp_libvirt_conn.unregisterCloseCallback()


def launch_thread_hyps_event(dict_hyps):
    # t = threading.Thread(name= 'events',target=events_from_hyps, args=[list_hostnames])

    t = ThreadHypEvents(name='hyps_events', dict_hyps=dict_hyps)
    t.daemon = True
    t.start()
    return t
