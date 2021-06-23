#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import time, os
import ipaddress
from api import app
from datetime import datetime, timedelta
from pprint import pprint

import requests

from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlTimeoutError

import logging as log

from .flask_rethink import RDB
db = RDB(app)
db.init_app(app)

from ..auth.authentication import *

from ..libv2.isardViewer import isardViewer
isardviewer = isardViewer()

from .apiv2_exc import *

from ..libv2.isardVpn import isardVpn
isardVpn = isardVpn()

from .helpers import _check, _parse_string, _parse_media_info, _disk_path

from .ds import DS 
ds = DS()

from .helpers import _check, _random_password

from subprocess import check_call, check_output

# os.environ['WG_HYPERS_NET']
# maximum_hypers=os.environ['WG_HYPERS_NET']
class ApiHypervisors():
    def __init__(self):
        None

    def hyper(self,hostname):
        data={}
        if hostname == 'localhost': hostname='isard-hypervisor'
        # Check if it is in database
        with app.app_context():
            hypervisor=r.table('hypervisors').get(hostname).run(db.conn)
        if hypervisor is None:
            # Hypervisor not in database
            with app.app_context():
                hyper_numbers=list(r.table('hypervisors').pluck('hypervisor_number').run(db.conn))
                hyper_numbers=[ n['hypervisor_number'] for n in hyper_numbers ]

            try:
                hypervisor_number = [ i  for i in range(0,self.hypervisors_max_networks()) if i not in hyper_numbers ][0]
                print(hypervisor_number)
            except:
                log.error('There are not hyper numbers available in range')
                return {'status':False,'msg':'There are not hyper numbers available in range','data':data}
            if not self.add_hyper(hostname,hypervisor_number,description="Added via api"): 
                log.error('Something went wrong when adding hyper to database')
                return {'status':False,'msg':'Something went wrong when adding hyper to database','data':data}
            log.info('Hypervisor '+hostname+'added to database')
        else:
            # Hypervisor already in database. Is asking for certs...
            hypervisor_number=hypervisor['hypervisor_number']
            # Lets check if it's fingerprint is already here
            self.update_fingerprint(hostname,hypervisor['port'])

        data['certs']=self.get_hypervisors_certs()
        data['number']=hypervisor_number

        try:
            requests.get('http://isard-engine:5555/engine_restart')
        except:
            log.error('Could not restart engine after adding hypervisor '+hostname)
        return {'status':True,'msg':'Hypervisor added','data':data}

    def add_hyper(self,hyp_id,hyp_number,port="2022",cap_disk=True,cap_hyper=True,enabled=True,description="Default hypervisor"):
        if not self.update_fingerprint(hyp_id,port): return False
        hypervisor={"capabilities": {
                        "disk_operations": cap_disk ,
                        "hypervisor": cap_hyper
                    } ,
                    "description": description ,
                    "detail": "" ,
                    "enabled": enabled ,
                    "hostname": hyp_id ,
                    "hypervisor_number": hyp_number ,
                    "hypervisors_pools": ["default"] ,
                    "id": hyp_id ,
                    "port": port ,
                    "status": "Offline" ,
                    "status_time": False ,
                    "uri": "" ,
                    "user": "root" ,
                    "viewer": {
                        "html5_ext_port": "443" ,
                        "proxy_hyper_host": hyp_id ,
                        "proxy_video": hyp_id ,
                        "spice_ext_port": "80" ,
                        "static": os.environ['WEPAPP_DOMAIN']
                    }
                }

        if cap_disk:
            for hp in hypervisor['hypervisors_pools']:
                with app.app_context():
                    paths=r.table('hypervisors_pools').get(hp).run(db.conn)['paths']
                for p in paths:
                    for i,path_data in enumerate(paths[p]):
                        if hyp_id not in path_data['disk_operations']:
                            path_data['disk_operations'].append(hyp_id)
                            paths[p][i]['disk_operations']=path_data['disk_operations']
                with app.app_context():
                    r.table('hypervisors_pools').get(hp).update({'paths':paths,'enabled':False}).run(db.conn)
        with app.app_context():
            r.table('hypervisors').insert(hypervisor).run(db.conn)
        return True

    def remove_hyper(self,hostname):
        with app.app_context():
            hypervisor=r.table('hypervisors').get(hostname).run(db.conn)
        for hp in hypervisor['hypervisors_pools']:
            with app.app_context():
                paths=r.table('hypervisors_pools').get(hp).run(db.conn)['paths']
            for p in paths:
                for i,path_data in enumerate(paths[p]):
                    if hostname in path_data['disk_operations']:
                        path_data['disk_operations'].remove(hostname)
                        paths[p][i]['disk_operations']=path_data['disk_operations']
            with app.app_context():
                r.table('hypervisors_pools').get(hp).update({'paths':paths,'enabled':False}).run(db.conn)

        with app.app_context():
            r.table('hypervisors').get(hostname).update({'enabled':False}).run(db.conn)
            time.sleep(2)
            r.table('hypervisors').get(hostname).update({'status':'Deleting'}).run(db.conn)
            time.sleep(2)
            r.table('hypervisors').get(hostname).delete().run(db.conn)
        try:
            requests.get('http://isard-engine:5555/engine_restart')
        except:
            log.error('Could not restart engine after adding hypervisor '+hostname)
        return {'status':True,'msg':'Revoved from database and engine restarted','data':{}}

    def hypervisors_max_networks(self):
        ### There will be much more hypervisor networks available than dhcpsubnets
        # nparent = ipaddress.ip_network(os.environ['WG_MAIN_NET'], strict=False)
        # max_hypers=len(list(nparent.subnets(new_prefix=os.environ['WG_HYPERS_NET'])))

        ## So get the max from dhcpsubnets
        nparent = ipaddress.ip_network(os.environ['WG_GUESTS_NETS'], strict=False)
        max_hypers=len(list(nparent.subnets(new_prefix=int(os.environ['WG_GUESTS_DHCP_MASK']))))
        return max_hypers

    def get_hypervisors_certs(self):
        certs={}
        path='/viewers'
        for subdir, dirs, files in os.walk(path):
            for file in files:
                with open(path+'/'+file, "r") as f:
                    certs[file]=f.read()
        with open('/sshkeys/id_rsa.pub','r') as id_rsa:
            certs['id_rsa.pub']=id_rsa.read()
        return certs

    def update_fingerprint(self,hostname,port):
        path='/sshkeys/known_hosts'
        if not os.path.exists(path): os.mknod(path)
        with open(path, 'r') as f:
            content=f.read()

        try:
            check_output(('ssh-keygen','-R',hostname,'-f',path), text=True).strip()
        except:
            log.error('Could not remove ssh key for '+hostname+':'+str(port))
            return False

        try:
            new_fingerprint=check_output(('ssh-keyscan','-p',port,'-t','rsa','-T','3',hostname), text=True).strip()
        except:
            log.error('Could not get ssh-keyscan for '+hostname+':'+str(port))
            return False

        if new_fingerprint not in content:
            with open(path, "a") as f:
                new_fingerprint=new_fingerprint+'\n'
                f.write(new_fingerprint)
            log.warning('Keys added for hypervisor '+hostname)
        else:
            log.warning('Keys already present for hypervisor'+hostname)
        return True

    def update_guest_addr(self, domain_id, data):
        with app.app_context():
            if not _check(r.table('domains').get(domain_id).update(data).run(db.conn),'replaced'):
                raise UpdateFailed 

    def get_hypervisor_vpn(self,hyp_id):
        return isardVpn.vpn_data('hypers','config','',hyp_id)

    def get_vlans(self):
        with app.app_context():
            interfaces=r.table('interfaces').run(db.conn)
        return [v.split('br-')[1] for v in interfaces if v['net'].startswith('br-')]


    def check(self,dict,action):
        #~ These are the actions:
        #~ {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
        if dict[action] or dict['unchanged']: 
            return True
        if not dict['errors']: return True
        return False