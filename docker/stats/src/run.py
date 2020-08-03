from threading import Thread

from sources.engine import Engine
from sources.operating_system import OperatingSystem
from sources.containers import Containers
from sources.hypervisor import Hypervisors

# ~ from sources.domains_events import DomainsEvents
# ~ from sources.domains import Domains

# ~ domains=Domains()
# ~ if domains.check() is not False:
    # ~ print('LIBVIRT DOMAINS MONITOR: OK')
    # ~ thread_domains = Thread(target = domains.stats)
    # ~ thread_domains.start()
# ~ else:
    # ~ print('LIBVIRT DOMAINS MONITOR: FAILED')  
    
# ~ domains_events=DomainsEvents()
# ~ if domains_events.check() is not False:
    # ~ print('LIBVIRT EVENT MONITOR: OK')
    # ~ thread_domains_events = Thread(target = domains_events.stats)
    # ~ thread_domains_events.start()
# ~ else:
    # ~ print('LIBVIRT EVENT MONITOR: FAILED')
    
engine=Engine()
if engine.check() is not False:
    print('ENGINE MONITOR: OK')
    thread_engine = Thread(target = engine.stats)
    thread_engine.start()
else:
    print('ENGINE MONITOR: FAILED')
    
ossys=OperatingSystem()
if ossys.check() is not False:
    print('OPERATING SYSTEM MONITOR: OK')
    thread_ossys = Thread(target = ossys.stats)
    thread_ossys.start()
else:
    print('OPERATING SYSTEM MONITOR: FAILED')
    
dock=Containers()
if dock.check() is not False:
    print('DOCKER MONITOR: OK')
    thread_dock_stats = Thread(target = dock.stats)
    thread_dock_stats.start()
else:
    print('DOCKER MONITOR: FAILED')
    
hyp=Hypervisors()
if hyp.check() is not False:
    print('HYPERVISOR MONITOR: OK')
    thread_hyp_stats = Thread(target = hyp.stats)
    thread_hyp_stats.start()
else:
    print('HYPERVISOR MONITOR: FAILED')
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
# ~ engine_work=engine.check()
# ~ if engine_work is False: 
    # ~ print("Engine not reacheable, disabling stats for engine")
# ~ else:
    # ~ print('Starting engine stats...')
    
# ~ ossys_work=ossys.stats()
# ~ if ossys_work is False: 
    # ~ print("SysStats not working, disabling system stats")
# ~ else:
    # ~ print('Starting System Stats...')
    
# ~ dock_work=dock.stats()
# ~ if dock_work is False: 
    # ~ print("Docker not reacheable, disabling stats for docker containers")
# ~ else:
    # ~ print('Starting dock stats...')
    
# ~ while True:
    # ~ if engine_work is not False: send(transform({"engine":engine.stats()})) 
    # ~ if ossys_work is not False:  send(transform({"system":ossys.stats()}))
    # ~ if dock_work is not False:  send(transform({"docker":dock.stats()}))
    # ~ time.sleep(10)
