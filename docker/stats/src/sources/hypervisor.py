import docker
import os, time, re
from time import sleep
from lib.carbon import Carbon
from lib.flask_rethink import RethinkDB
import rethinkdb as r

import collections
import socket

c=Carbon()
dbconn=RethinkDB()

ip_squid = socket.gethostbyname('isard-squid')
ip_websockify = socket.gethostbyname('isard-websockify')

from lib.helpers import cu, execute

class Hypervisors():
    def __init__(self, interval=5):
        self.interval = interval
        self.client=None
        
    def check(self):
        ## We should check if we can c
        try:
            sleep(10)
            self.client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
            self.container_hyp=self.client.containers.get('isard-hypervisor')
            return True
        except:
            return False
        # ~ return True if os.path.isfile('/var/run/docker.sock') else False
        
    def stats(self):
        tmp_events=['started','connect','disconnect','connect','disconnect','stopped']
        tmp_event=0
        while True:
            cmd_ss = 'ss -t state established -p "( sport > 5900 )"'
            # ~ cmd_ss = 'ss -t state established -p "( sport > 5900 )" |grep kvm'
            cmd_virsh = 'virsh list'
            # ~ cmd_virsh = 'virsh list |grep -i running|wc -l'
            
            raw = self.container_hyp.exec_run(cmd_virsh)
            if raw[0] != 0:
                print('Error in command: '+cmd_virsh)
                break
            try:
                num_desktops = int(len(raw[1].decode("utf-8").split('\n'))-4)
            except:
                num_desktops = 0
                
            raw = self.container_hyp.exec_run(cmd_ss)
            if raw[0] != 0:
                print('Error in command: '+cmd_ss)
                break
            # ~ print(raw[1].decode("utf-8"))
            
            data = raw[1].decode("utf-8").splitlines()
            data.pop(0)
            out_ss='\n'.join(data)
            #print(out_ss)
            port_ip = [a.split(':')[1] for a in out_ss.splitlines()]
            resum_connections = collections.Counter([i.split()[1] for i  in set(port_ip)])

            viewers_spice = resum_connections[ip_squid]
            viewers_websockify = resum_connections[ip_websockify]
            total_viewers = viewers_spice + viewers_websockify
            
            # ~ print({'domains':{'started':num_desktops},
                            # ~ 'domains.viewers':{'total':total_viewers, 'spice-client':viewers_spice,'vnc-html5':viewers_websockify}})
            
            ########### GRAFANA
            c.send2carbon({'domains':{'started':num_desktops},
                            'domains.viewers':{'total':total_viewers, 'spice-client':viewers_spice,'vnc-html5':viewers_websockify}})

            return
            ########### RETHINK
            event=tmp_events[tmp_event]
            protocol='spice-client'
            domain='linkatv220200428'
            usuari='293087492P'
            
            with dbconn as conn:
                ## Check if domain exists
                if event in ['started','stopped']:
                    if r.table('domains').get(domain).run(conn) is None:
                        dom={'id':domain,
                                'user':usuari,
                                'cpu':False,
                                'mem':False,
                                'disk_rd':False,
                                'disk_wr':False}
                        r.table('domains').insert(dom).run(conn)
                    r.table('run').insert({'domain':domain,'event':event,'when':time.time()}).run(conn)

                if event in ['connect','disconnect']:
                    r.table('viewer').insert({'domain':domain,'event':event,'when':time.time(),'protocol':protocol}).run(conn)                    

            with dbconn as conn:
                nested = r.table("domains").get(domain).merge(lambda run:
                    { 'run': r.table('run').get_all(run['id'],
                                           index='domain').coerce_to('array') }
                ).merge(lambda viewer:
                    { 'viewer': r.table('viewer').get_all(viewer['id'],
                                           index='domain').coerce_to('array') }
                ).run(conn)
            #print(nested)

            tmp_event+=1
            if tmp_event > len(tmp_events)-1: tmp_event = 0
            sleep(self.interval)                
                
                
                
                
                
                
                
                
                
                # ~ r.table('domains').filter({'id':domain}).is_empty().do(lambda empty:
                    # ~ r.branch((empty == True),
                        # ~ r.table('domains').insert(dom),
                        # ~ r.table('run').insert({'id':time.time()}))).run(conn)
                        
                # ~ ).run(conn)
                # ~ .update(data, conflict='update').run(conn)
            
            # ~ data={'id':usuari,
                    # ~ 'domains':{domain:{'started':time.time(),
                                                    # ~ 'paused':[],
                                                    # ~ 'resumed':[],
                                                    # ~ 'stopped':False,
                                                    # ~ 'viewer':{protocol:{'intervals':[{'connect':time.time(),'disconnect':time.time()+100}]}},
                                                    # ~ 'cpu':3.4,
                                                    # ~ 'mem':37
                                                  # ~ }
                                # ~ }
                # ~ }
            
            # ~ if event == 'started':
                # ~ r.table('trace').update
                # ~ r.table("users").get(10001).update(
                    # ~ {"notes": r.row["notes"].default([]).append(new_note)}
                # ~ ).run(conn)



            # ~ with dbconn as conn:
                # ~ r.table('trace').insert(new_data).do(lambda doc:
                    # ~ r.branch((doc['inserted'] != 0),
                        # ~ None,
                        # ~ r.table('trace').get(data['id']).update({'domains':{'domain'}})
                        
                        
                        # ~ r.table('log').insert({'time': r.now(), 'response': doc, 'result': 'ok'}),
                        # ~ r.table('log').insert({'time': r.now(), 'response': doc, 'result': 'error'}))
                # ~ ).run(conn)             
                
                # ~ if r.table('trace').filter({}).is_empty().do(
                # ~ ).run(conn)
                
                # ~ r.table('trace').insert(data, conflict='update').run(conn)




                    

