import requests
from pprint import pprint
#!/usr/bin/python
import time
import libvirt
import sys, os

from lib.carbon import Carbon
c=Carbon()

# virDomainEventType is emitted during domain lifecycles (see libvirt.h)
VIR_DOMAIN_EVENT_MAPPING = {
    0: "VIR_DOMAIN_EVENT_DEFINED",
    1: "VIR_DOMAIN_EVENT_UNDEFINED",
    2: "VIR_DOMAIN_EVENT_STARTED",
    3: "VIR_DOMAIN_EVENT_SUSPENDED",
    4: "VIR_DOMAIN_EVENT_RESUMED",
    5: "VIR_DOMAIN_EVENT_STOPPED",
    6: "VIR_DOMAIN_EVENT_SHUTDOWN",
    7: "VIR_DOMAIN_EVENT_PMSUSPENDED",
}

# virDomainState
VIR_DOMAIN_STATE_MAPPING = {
    0: "VIR_DOMAIN_NOSTATE",
    1: "VIR_DOMAIN_RUNNING",
    2: "VIR_DOMAIN_BLOCKED",
    3: "VIR_DOMAIN_PAUSED",
    4: "VIR_DOMAIN_SHUTDOWN",
    5: "VIR_DOMAIN_SHUTOFF",
    6: "VIR_DOMAIN_CRASHED",
    7: "VIR_DOMAIN_PMSUSPENDED",
}

class Description(object):
    __slots__ = ('desc', 'args')

    def __init__(self, *args, **kwargs):
        self.desc = kwargs.get('desc')
        self.args = args

    def __str__(self):  # type: () -> str
        return self.desc

    def __getitem__(self, item):  # type: (int) -> str
        try:
            data = self.args[item]
        except IndexError:
            return self.__class__(desc=str(item))

        if isinstance(data, str):
            return self.__class__(desc=data)
        elif isinstance(data, (list, tuple)):
            desc, args = data
            return self.__class__(*args, desc=desc)

        raise TypeError(args)
        
DOM_EVENTS = Description(
    ("Defined", ("Added", "Updated", "Renamed", "Snapshot")),
    ("Undefined", ("Removed", "Renamed")),
    ("Started", ("Booted", "Migrated", "Restored", "Snapshot", "Wakeup")),
    ("Suspended", ("Paused", "Migrated", "IOError", "Watchdog", "Restored", "Snapshot", "API error", "Postcopy", "Postcopy failed")),
    ("Resumed", ("Unpaused", "Migrated", "Snapshot", "Postcopy")),
    ("Stopped", ("Shutdown", "Destroyed", "Crashed", "Migrated", "Saved", "Failed", "Snapshot", "Daemon")),
    ("Shutdown", ("Finished", "On guest request", "On host request")),
    ("PMSuspended", ("Memory", "Disk")),
    ("Crashed", ("Panicked",)),
)

GRAPHICS_PHASES = Description("Connect", "Initialize", "Disconnect")

libvirt.virEventRegisterDefaultImpl()

        
class DomainsEvents():
    def __init__(self,uri='qemu+unix:///system?socket=/var/run/libvirt/libvirt-sock-ro'):
        self.uri=uri
        self.thread=None
        # ~ self.dom_started={}
        self.viewer={}
        
    def stats(self):
        try:
            # register start/stop events
            # ~ self.conn_register_event_id_lifecycle(self.conn)
            # register viewers
            self.conn_register_event_id_graphics(self.conn)
            # event loop
            while True:
                libvirt.virEventRunDefaultImpl()
        except Exception as e:
            print(e)
            return False
            
    def check(self):
        try:
            self.conn=libvirt.openReadOnly(self.uri)
            if self.conn == None:
                print('Failed to open connection to the hypervisor')
                return False
            return True
        except Exception as e:
            print(e)
            return False

    '''START, STOP ...   '''
    def event_lifecycle_cb(self, conn, dom, event, detail, opaque):
        # ~ c.send2carbon({"docker":d})
        # ~ sleep(self.interval)
        if VIR_DOMAIN_EVENT_MAPPING.get(event, "?") == "VIR_DOMAIN_EVENT_STARTED":
            if dom.name().startswith('_'):
                user=dom.name().split('_')[1]
            print('User: '+user+'\nDomain started: '+dom.name())
        if VIR_DOMAIN_EVENT_MAPPING.get(event, "?") == "VIR_DOMAIN_EVENT_STOPPED":
            if dom.name().startswith('_'):
                user=dom.name().split('_')[1]
            print('User: '+user+'\nDomain stopped: '+dom.name())
            
        # ~ print("")
        # ~ print("=-" * 25)
        # ~ print("%s: event: %s (%s)" % (dom.name(), VIR_DOMAIN_EVENT_MAPPING.get(event, "?"), event))
        # ~ print("%s: state: %s (%s)" % (dom.name(), VIR_DOMAIN_STATE_MAPPING.get(dom.state()[0], "?"), dom.state()[0]))
        # ~ print("=-" * 25)


    def conn_register_event_id_lifecycle(self, conn):
        self.conn.domainEventRegisterAny(
            None,
            libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE,
            self.event_lifecycle_cb,
            self.conn)
    
    '''VIEWERS ...   '''
    def event_graphics_cb(self, conn, dom, phase, localAddr, remoteAddr, authScheme, subject, opaque):
        if dom.name() not in self.viewer.keys():
            self.viewer[dom.name()]={'spice-client':{'start':0,
                                                    'stop':0,
                                                    'remote':remoteAddr,
                                                    'channels_open':0},
                                    'vnc-html5':{'start':0,
                                                    'stop':0,
                                                    'remote':remoteAddr,
                                                    'channels_open':0}
                                    }
                                                    
        viewer='vnc-html5' if authScheme == 'vnc' else 'spice-client'
        # ~ if viewer=='vnc-html5':
            # ~ print(str(GRAPHICS_PHASES[phase])+' - '+authScheme)
        if str(GRAPHICS_PHASES[phase]) == 'Connect':
            self.viewer[dom.name()][viewer]['start']=time.time()
            if self.viewer[dom.name()][viewer]['channels_open']==0:
                c.send2carbon({"domain_events."+viewer:{"open": '1'}})   
            self.viewer[dom.name()][viewer]['channels_open']+=1
        if str(GRAPHICS_PHASES[phase]) == 'Disconnect':
            self.viewer[dom.name()][viewer]['stop']=time.time()
            self.viewer[dom.name()][viewer]['channels_open']-=1
            if self.viewer[dom.name()][viewer]['channels_open']==0:
                c.send2carbon({"domain_events."+viewer:{"closed": '1'}})
                c.send2carbon({"domain_events."+viewer:{"use": str(round(self.viewer[dom.name()][viewer]['stop']-self.viewer[dom.name()][viewer]['start']))}})
                del self.viewer[dom.name()]
                return

            # ~ print(dom.name()+'  viewer lifecicle:')
            # ~ pprint(self.viewer[dom.name()])
            
            
            # ~ print('Has been connected to '+viewer+' for '+str(round(self.viewer[dom.name()][viewer]['stop']-self.viewer[dom.name()][viewer]['start']))+'seconds')
            # ~ del self.viewer[dom.name()]
        # ~ if GRAPHICS[phase] == 'Connect vnc':
            # ~ self.viewer[dom.name()]['vnc-client']={'start':time.time(),
                                                    # ~ 'stop':0,
                                                    # ~ 'remote':remoteAddr,
                                                    # ~ 'auth':authScheme,
                                                    # ~ 'subject':subject}
        # ~ print("myDomainEventGraphicsCallback: Domain %s(%s) %s %s %s %s" % (
            # ~ dom.name(), dom.ID(), GRAPHICS_PHASES[phase], authScheme, subject, opaque))
        # ~ if VIR_DOMAIN_EVENT_MAPPING.get(event, "?") == "VIR_DOMAIN_EVENT_STARTED":
            # ~ if dom.name().startswith('_'):
                # ~ user=dom.name().split('_')[1]
            # ~ print('User: '+user+'\nDomain started: '+dom.name())
        # ~ if VIR_DOMAIN_EVENT_MAPPING.get(event, "?") == "VIR_DOMAIN_EVENT_STOPPED":
            # ~ if dom.name().startswith('_'):
                # ~ user=dom.name().split('_')[1]
            # ~ print('User: '+user+'\nDomain stopped: '+dom.name())
            
        # ~ print("")
        # ~ print("=-" * 25)
        # ~ print("%s: event: %s (%s)" % (dom.name(), VIR_DOMAIN_EVENT_MAPPING.get(event, "?"), event))
        # ~ print("%s: state: %s (%s)" % (dom.name(), VIR_DOMAIN_STATE_MAPPING.get(dom.state()[0], "?"), dom.state()[0]))
        # ~ print("=-" * 25)
            
    def conn_register_event_id_graphics(self, conn): 
        self.conn.domainEventRegisterAny(
            None,
            libvirt.VIR_DOMAIN_EVENT_ID_GRAPHICS,
            self.event_graphics_cb,
            self.conn)
                                
                                
                                
                                
                                
    def _iterdict(self,d):
      alert=[]
      for k,v in d.items():
         if isinstance(v, dict):
             self._iterdict(v)
         else:
             if type(v) is bool and v is False:
                 alert.append(k)
      return alert  

















