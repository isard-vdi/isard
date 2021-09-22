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

import traceback

import requests

from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlTimeoutError
from rethinkdb.errors import ReqlNonExistenceError

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

from .helpers import _check, _parse_string, _parse_media_info, _disk_path, generate_db_media

from .ds import DS 
ds = DS()

from .helpers import _check, _random_password

from subprocess import check_call, check_output

import socket

# os.environ['WG_HYPERS_NET']
# maximum_hypers=os.environ['WG_HYPERS_NET']
class ApiHypervisors():
    def __init__(self):
        None

    def hyper(self,hostname,port="2022",
                cap_disk=True,cap_hyper=True,enabled=False,
                description="Default hypervisor",
                browser_port='443',
                spice_port='80',
                isard_static_url=os.environ['DOMAIN'],
                isard_video_url=os.environ['DOMAIN'],
                isard_proxy_hyper_url='isard-hypervisor',
                isard_hyper_vpn_host='isard-vpn'):
        data={}

        # Check if it is in database
        with app.app_context():
            hypervisor=r.table('hypervisors').get(hostname).run(db.conn)
        if hypervisor is None:
            # Hypervisor not in database
            with app.app_context():
                hyper_numbers=list(r.table('hypervisors').pluck('hypervisor_number').run(db.conn))
                hyper_numbers=[ n['hypervisor_number'] for n in hyper_numbers ]

            # if hostname == 'isard-hypervisor': 
            #     hypervisor_number = 0
            # else:
            try:
                hypervisor_number = [ i  for i in range(1,999) if i not in hyper_numbers ][0]
            except:
                log.error('There are not hyper numbers available in range')
                return {'status':False,'msg':'There are not hyper numbers available in range','data':data}

            if not self.check(self.add_hyper(hostname,
                                hypervisor_number,
                                port=port,
                                cap_disk=cap_disk,
                                cap_hyper=cap_hyper,
                                enabled=False,
                                browser_port=str(browser_port),
                                spice_port=str(spice_port),
                                isard_static_url=isard_static_url,
                                isard_video_url=isard_video_url,
                                isard_proxy_hyper_url=isard_proxy_hyper_url,
                                isard_hyper_vpn_host=isard_hyper_vpn_host,
                                description="Added via api"),'inserted'): 

                return {'status':False,'msg':'Unable to ssh-keyscan '+hostname+' port '+str(port)+'. Please ensure the port is opened in the hypervisor','data':data}
            log.info('Hypervisor '+hostname+'added to database')
        else:
            result= self.add_hyper(hostname,
                        hypervisor['hypervisor_number'],
                        port=port,
                        cap_disk=cap_disk,
                        cap_hyper=cap_hyper,
                        enabled=hypervisor['enabled'],
                        browser_port=str(browser_port),
                        spice_port=str(spice_port),
                        isard_static_url=isard_static_url,
                        isard_video_url=isard_video_url,
                        isard_proxy_hyper_url=isard_proxy_hyper_url,
                        isard_hyper_vpn_host=isard_hyper_vpn_host,
                        description="Added via api")
            #{'deleted': 0, 'errors': 0, 'inserted': 0, 'replaced': 1, 'skipped': 0, 'unchanged': 0}
            if not result: return  {'status':False,'msg':'Unable to ssh-keyscan '+hostname+' port '+str(port)+'. Please ensure the port is opened in the hypervisor','data':data}
            if result['replaced'] and hypervisor['enabled']:
                ## We should restart engine
                self.engine_restart()
            elif result['unchanged'] or not hypervisor['enabled']:
                pass
            else:
                return {'status':False,'msg':'Unable to ssh-keyscan '+hostname+' port '+str(port)+'. Please ensure the port is opened in the hypervisor','data':data}

            # Hypervisor already in database. Is asking for certs...
            hypervisor_number=hypervisor['hypervisor_number']
            # Lets check if it's fingerprint is already here
            # self.update_fingerprint(hostname,hypervisor['port'])

        data['certs']=self.get_hypervisors_certs()
        data['number']=hypervisor_number

        return {'status':True,'msg':'Hypervisor added','data':data}

    def add_hyper(self,hyp_id,hyp_number,port="2022",
                    cap_disk=True,cap_hyper=True,enabled=False,
                    description="Default hypervisor",
                    browser_port='443',
                    spice_port='80',
                    isard_static_url=os.environ['DOMAIN'],
                    isard_video_url=os.environ['DOMAIN'],
                    isard_proxy_hyper_url='isard-hypervisor',
                    isard_hyper_vpn_host='isard-vpn'):
        # If we can't connect why we should add it? Just return False!
        if not self.update_fingerprint(hyp_id,port): return False

        hypervisor={"capabilities": {
                        "disk_operations": cap_disk ,
                        "hypervisor": cap_hyper
                    } ,
                    "description": description ,
                    "detail": "" ,
                    "enabled": enabled ,
                    "hostname": hyp_id ,
                    "isard_hyper_vpn_host": isard_hyper_vpn_host,
                    "hypervisor_number": hyp_number ,
                    "hypervisors_pools": ["default"] ,
                    "id": hyp_id ,
                    "port": port ,
                    "status": "Offline" ,
                    "status_time": False ,
                    "uri": "" ,
                    "user": "root" ,
                    "viewer": {
                        "static": isard_static_url,         # isard-static nginx
                        "proxy_video": isard_video_url ,    # Video Proxy Host
                        "spice_ext_port": spice_port ,      # 80
                        "html5_ext_port": browser_port ,    # 443
                        "proxy_hyper_host": isard_proxy_hyper_url  # Viewed from isard-video
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
                    result = r.table('hypervisors_pools').get(hp).update({'paths':paths,'enabled':False}).run(db.conn)
        with app.app_context():
            result=r.table('hypervisors').insert(hypervisor, conflict='update').run(db.conn)
        return result

    def enable_hyper(self,hostname):
        with app.app_context():
            hypervisor=r.table('hypervisors').get(hostname).run(db.conn)
        if hypervisor == None: return {'status':False,'msg':'Hypervisor not found','data':{}}

        with app.app_context():
            r.table('hypervisors').get(hostname).update({'enabled':True}).run(db.conn)

        self.engine_restart()
        return {'status':True,'msg':'Hypervisor enabled','data':{}}

    def remove_hyper(self,hostname,restart=True):
        self.stop_hyper_domains(hostname)
        with app.app_context():
            hypervisor=r.table('hypervisors').get(hostname).run(db.conn)
        if hypervisor == None: return {'status':False,'msg':'Hypervisor not found','data':{}}
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
            r.table('hypervisors').get(hostname).update({'enabled':False, 'status':'Deleting'}).run(db.conn)
            now = time.time()

            while time.time()-now < 10:
                time.sleep(1)
                try:
                    r.table('hypervisors').get(hostname)
                except ReqlNonExistenceError:
                    return {'status':True,'msg':'Removed from database','data':{}}

            # time.sleep(2)
            # r.table('hypervisors').get(hostname).update({'status':'Deleting'}).run(db.conn)
            # time.sleep(2)
            # r.table('hypervisors').get(hostname).delete().run(db.conn)

        #if restart: self.engine_restart()
        return {'status':True,'msg':'Hypervisor yet in database, timeout waiting to delete','data':{}}

    def stop_hyper_domains(self,hostname):
        with app.app_context():
            domains=list(r.table('domains').get_all('Started', index='status').filter({'hyp_started':hostname}).update({'status':'Stopping'}).run(db.conn))
            time.sleep(1)
        while len(list(r.table('domains').get_all('Started', index='status').filter({'hyp_started':hostname}).run(db.conn))):
            time.sleep(1)

    def engine_restart(self):
        try:
            res = requests.get('http://isard-engine:5555/engine_restart')
        except:
            ## The procedure jusr restart engine, so no answer is expected:
            return True
            log.error('Could not restart engine after adding hypervisor')
            return False

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

        try:
            print('ssh-keygen','-R','['+hostname+']:'+str(port),'-f',path)
            check_output(('ssh-keygen','-R','['+hostname+']:'+str(port),'-f',path), text=True).strip()
        except:
            log.error('Could not remove ssh key for ['+hostname+']'+str(port))
            return False
        try:
            check_output(('ssh-keygen','-R','['+socket.gethostbyname(hostname)+']:'+str(port),'-f',path), text=True).strip()
        except:
            log.error('Could not remove ssh key for ['+hostname+']'+str(port))
            return False

        try:
            new_fingerprint=check_output(('ssh-keyscan','-p',port,'-t','rsa','-T','3',hostname), text=True).strip()
        except:
            log.error('Could not get ssh-keyscan for '+hostname+':'+str(port))
            return False

        with open(path, "a") as f:
            new_fingerprint=new_fingerprint+'\n'
            f.write(new_fingerprint)
            log.warning('Keys added for hypervisor '+hostname+':'+str(port))

        return True

    def update_guest_addr(self, domain_id, data):
        with app.app_context():
            if not _check(r.table('domains').get(domain_id).update(data).run(db.conn),'replaced'):
                raise UpdateFailed 

    def update_wg_address(self, mac, data):
        with app.app_context():
            try:
                domain_id = list(r.table('domains').get_all(mac, index='wg_mac').run(db.conn))[0]['id']
                r.table('domains').get(domain_id).update(data).run(db.conn)
                return domain_id
            except:
                # print(traceback.format_exc())
                return False

    def get_hypervisor_vpn(self,hyp_id):
        return isardVpn.vpn_data('hypers','config','',hyp_id)

    def get_vlans(self):
        with app.app_context():
            interfaces=r.table('interfaces').run(db.conn)
        return [v.split('br-')[1] for v in interfaces if v['net'].startswith('br-')]

    def add_vlans(self,vlans):
        for vlan in vlans:
            new_vlan = {'id': 'v'+vlan,
                            'name': 'Vlan '+vlan,
                            'description': 'Infrastructure vlan',
                            'ifname': 'br-'+vlan,
                            'kind': 'bridge',
                            'model': 'virtio',
                            'net': 'br-'+vlan,
                            'qos_id': False,
                            'allowed': {
                                'roles': ['admin'],
                                'categories': False,
                                'groups': False,
                                'users': False}
                            }
            with app.app_context():
                r.db('isard').table('interfaces').insert(new_vlan).run(db.conn)

    def update_media_found(self,medias):
        with app.app_context():
            db_medias = list(r.table('media').pluck('path_downloaded').run(db.conn))
        db_medias_paths = [dbm['path_downloaded'] for dbm in db_medias]

        medias_paths=[m[0] for m in medias] 
        new = list(set(medias_paths)-set(db_medias_paths))
        # missing = list(set(db_medias_paths)-set(medias_paths))

        for n in new:
            for m in medias:
                if m[0] == n: 
                    with app.app_context():
                        db_medias = r.table('media').insert(generate_db_media(m[0],m[1])).run(db.conn)
                        log.info('Added new media from hypervisor: '+m[0])
                        print('Added new media from hypervisor: '+m[0])

    def update_disks_found(self,disks):
        with app.app_context():
            db_disks = list(r.table('domains').get_all('desktop', index='kind').pluck({'create_dict':{'hardware':{'disks'}}}).run(db.conn))
        db_disks_paths = [d[0]['file'] for d in [ds['create_dict']['hardware']['disks'] for ds in db_disks if ds['create_dict']['hardware'].get('disks',False) and len(ds['create_dict']['hardware']['disks'])]]

        disks_paths=[d[0] for d in disks] 
        new = list(set(disks_paths)-set(db_disks_paths))
        # missing = list(set(db_medias_paths)-set(medias_paths))

        for n in new:
            for m in disks:
                if m[0] == n: 
                    with app.app_context():
                        db_medias = r.table('media').insert(generate_db_media(m[0],m[1])).run(db.conn)
                        log.info('Added new disk from hypervisor: '+m[0])
                        print('Added new disk from hypervisor: '+m[0])

    def check(self,dict,action):
        #~ These are the actions:
        #~ {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
        if not dict: return False
        if dict[action] or dict['unchanged']: 
            return True
        if not dict['errors']: return True
        return False