# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import rethinkdb as r
import time, sys
from .log import *
from .lib import *

from string import digits, ascii_lowercase
import random

class Populate(object):
    def __init__(self):
        cfg=loadConfig()
        self.cfg=cfg.cfg()
        try:
            print(self.cfg['RETHINKDB_HOST'])
            self.conn = r.connect( self.cfg['RETHINKDB_HOST'],self.cfg['RETHINKDB_PORT'],self.cfg['RETHINKDB_DB']).repl()
        except Exception as e:
            log.error('Database not reacheable at '+self.cfg['RETHINKDB_HOST']+':'+self.cfg['RETHINKDB_PORT'])
            exit
        self.p = Password()
        self.passwd = self.p.encrypt(self.cfg['WEBAPP_ADMIN_PWD'])
        if self.is_database_created() is True:
            log.info('Database engine already present...')
        else:
            log.error('Something went wrong when initially populating db')
            exit
            # ~ self.defaults()
            
        
    '''
    DATABASE
    '''

    def is_database_created(self):
        print(self.update_virtinstalls())
        try:
            if not r.db_list().contains(self.cfg['RETHINKDB_DB']).run():
                log.warning('Database {} not found, creating new one.'.format(self.cfg['RETHINKDB_DB']))
                r.db_create(self.cfg['RETHINKDB_DB']).run()
                log.info('Populating database with tables and initial data')
                self.check_integrity()
                return True
            log.info('Database {} found.'.format(self.cfg['RETHINKDB_DB']))
            return True
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            log.error(exc_type, fname, exc_tb.tb_lineno)
            return False

    # ~ def defaults(self):
        # ~ return self.check_integrity()

    def check_integrity(self,commit=True):
        dbtables=r.table_list().run()
        newtables=['roles','categories','groups','users','vouchers',
                'hypervisors','hypervisors_pools','interfaces',
                'graphics','videos','disks','domains','domains_status','domains_status_history',
                'virt_builder','virt_install','builders','media',
                'boots','hypervisors_events','hypervisors_status','hypervisors_status_history',
                'disk_operations','hosts_viewers','places',
                'scheduler_jobs','backups','config','engine',
                'qos_net','qos_disk',
                   ]
        tables_to_create=list(set(newtables) - set(dbtables))
        d = {k:v for v,k in enumerate(newtables)}
        tables_to_create.sort(key=d.get)
        tables_to_delete=list(set(dbtables) - set(newtables))
        print(tables_to_create)
        if not commit:
            return {'tables_to_create':tables_to_create,'tables_to_delete':tables_to_delete}
        else:
            for t in tables_to_create:
                try:
                    table=t
                    if table.startswith('hypervisors_status'): table='hypervisors_status'
                    if table.startswith('domains_status'): table='domains_status'
                    log.info('Creating new table: '+t)
                    #CREATING TABLES WITH eval self.{name_of_table}
                    log.info('  Result: '+str(eval('self.'+table+'()')))
                except Exception as e:
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    log.error(exc_type, fname, exc_tb.tb_lineno)
                    return False                
            for t in tables_to_delete:
                try:
                    log.info('Deleting old table: '+t)
                    log.info('  Result: '+str(r.table_drop(t).run()))
                except Exception as e:
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    log.error(exc_type, fname, exc_tb.tb_lineno)
                    return False                  
        return True

    '''
    CONFIG
    '''

    def config(self):
        
            if not r.table_list().contains('config').run():
                log.warning("Table config not found, creating new one.")
                r.table_create('config', primary_key='id').run()
                self.result(r.table('config').insert([{'id': 1,
                                                       'auth': {'local': {'active': True},
                                                                'ldap': {'active': False,
                                                                         'ldap_server': 'ldap://ldap.domain.org',
                                                                         'bind_dn': 'dc=domain,dc=org'}},
                                                        'disposable_desktops':{'active': False},
                                                        'voucher_access':{'active': False},
                                                        'engine':{  'intervals':{   'status_polling':10,
                                                                                    'time_between_polling': 5,
                                                                                    'test_hyp_fail': 20,
                                                                                    'background_polling': 10,
                                                                                    'transitional_states_polling': 2},
                                                                    'ssh':{'paramiko_host_key_policy_check': False},
                                                                    'stats':{'active': True,
                                                                            'max_queue_domains_status': 10,
                                                                            'max_queue_hyps_status': 10,
                                                                            'hyp_stats_interval': 5
                                                                            },
                                                                    'log':{
                                                                            'log_name':  'isard',
                                                                            'log_level': 'WARNING',
                                                                            'log_file':  'msg.log'
                                                                    },
                                                                    'timeouts':{
                                                                            'ssh_paramiko_hyp_test_connection':   4,
                                                                            'timeout_trying_ssh': 2,
                                                                            'timeout_trying_hyp_and_ssh': 10,
                                                                            'timeout_queues': 2,
                                                                            'timeout_hypervisor': 10,
                                                                            'libvirt_hypervisor_timeout_connection': 3,
                                                                            'timeout_between_retries_hyp_is_alive': 1,
                                                                            'retries_hyp_is_alive': 3
                                                                            }},
                                                        'grafana':{'active':False,'url':'','hostname':'isard-grafana','carbon_port':2004,"interval": 5},
                                                        'version':0,
                                                        'shares':{'templates':False,'isos':False},
                                                        'resources': {'code': False,
                                                                    'url':'https://repository.isardvdi.com'}
                                                       }], conflict='update').run())
                log.info("Table config populated with defaults.")
                return True
            else:
                return False

    '''
    BACKUPS
    '''

    def backups(self):
        
            if not r.table_list().contains('backups').run():
                log.info("Table backups not found, creating and populating defaults...")
                r.table_create('backups', primary_key="id").run()
            return True                

    '''
    USERS
    Updated in Domains for
    '''

    def users(self):
            if not r.table_list().contains('users').run():
                log.info("Table users not found, creating...")
                r.table_create('users', primary_key="id").run()

                if r.table('users').get('admin').run() is None:
                    usr = [{'id': 'local-default-admin-admin',
                           'name': 'Administrator',
                           'provider': 'local',
                           'category': 'default',                           
                           'uid': 'admin',
                           'username': 'admin',
                           'active': True,
                           'accessed': time.time(),
                           'password': self.passwd,
                           'role': 'admin',
                           'group': 'default-default',
                           'email': 'admin@isard.io',
                           'photo': False,
                           'quota': False
                           }]
                    self.result(r.table('users').insert(usr, conflict='update').run())
                    log.info("  Inserted default admin  username with password defined in isardvdi.cfg")
            self.index_create('users',['provider','uid','category','group'])
            return True

    '''
    VOUCHERS
    Grant access on new voucher
    '''

    def vouchers(self):
        
            if not r.table_list().contains('vouchers').run():
                log.info("Table vouchers not found, creating...")
                r.table_create('vouchers', primary_key="id").run()
            return True


    '''
    ROLES
    '''

    def roles(self):
        
            if not r.table_list().contains('roles').run():
                log.info("Table roles not found, creating and populating...")
                r.table_create('roles', primary_key="id").run()
                self.result(r.table('roles').insert([{'id': 'user',
                                                      'name': 'User',
                                                      'description': 'Can create desktops and start it'
                                                      },
                                                     {'id': 'advanced',
                                                      'name': 'Advanced',
                                                      'description': 'Can create desktops and templates and start desktops'
                                                      },
                                                     {'id': 'manager',
                                                      'name': 'Manager',
                                                      'description': 'Can manage users, desktops, templates and media in a category'
                                                      },                                                      
                                                     {'id': 'admin',
                                                      'name': 'Administrator',
                                                      'description': 'Is God'
                                                      }]).run())
            return True

    '''
    CATEGORIES
    '''

    def categories(self):
        
            if not r.table_list().contains('categories').run():
                log.info("Table categories not found, creating...")
                r.table_create('categories', primary_key="id").run()

                if r.table('categories').get('admin').run() is None:
                    self.result(r.table('categories').insert([{'id': 'default',
                                                               'name': 'Default',
                                                               'description': 'Default category',
                                                               'frontend': True,
                                                               'quota': False,
                                                               'limits': False
                                                               }]).run())                                                    
            return True

    '''
    GROUPS
    '''

    def groups(self):
        
        if not r.table_list().contains('groups').run():
            log.info("Table groups not found, creating...")
            r.table_create('groups', primary_key="id").run()

            if r.table('groups').get('default').run() is None:
                self.result(r.table('groups').insert([{'id': 'default-default',
													   'uid': 'default',
													   'parent_category': 'default',
													   'enrollment': {'manager':False,'advanced':False,'user':False},
                                                       'name': 'Default',
                                                       'description': '[Default] Default group',
                                                       'quota': False,
                                                       'limits': False
                                                       }]).run())                                                                                                              
        return True

    '''
    QOS_NETWORK
    '''

    def qos_net(self):
        if not r.table_list().contains('qos_net').run():
            log.info("Table qos_net not found, creating and populating default network...")
            r.table_create('qos_net', primary_key="id").run()
            self.result(r.table('qos_net').insert([{
                'id': 'unlimited',
                'name': 'Unlimited',
                'description': 'Unlimited network throughput',
                "bandwidth": {
                   "inbound": {
                       "@average": 0,
                       "@peak": 0,
                       "@floor": 0,
                       "@burst": 0
                   },
                   "outbound": {
                       "@average": 0,
                       "@peak": 0,
                       "@burst": 0
                   }
                },
                'allowed': {
                   'roles': ['admin'],
                   'categories': False,
                   'groups': False,
                   'users': False}
                }]).run())            
            self.result(r.table('qos_net').insert([{
                'id': 'limit1M',
                'name': 'limit up and down to 1Mbps',
                'description': 'limit upstream and downstream to 1Mbps(125KBytes/s) and burst of 10Mbps for a max 100MB transfer.',
                "bandwidth": {
                   "inbound": {
                       "@average": 125,
                       "@peak": 1250,
                       "@floor": 0,
                       "@burst": 12500
                   },
                   "outbound": {
                       "@average": 125,
                       "@peak": 1250,
                       "@burst": 12500
                   }
                },
                'allowed': {
                   'roles': ['admin'],
                   'categories': False,
                   'groups': False,
                   'users': False}
                }]).run())

    '''
    QOS_DISK
    '''

    def qos_disk(self):
        if not r.table_list().contains('qos_disk').run():
            log.info("Table qos_disk not found, creating and populating default network...")
            r.table_create('qos_disk', primary_key="id").run()
            self.result(r.table('qos_disk').insert([{
                'id': 'unlimited',
                'name': 'Unlimited',
                'description': 'Unlimited BW/IO to disk',
                "iotune":{
                    # throughput limit in bytes per second.
                    "read_bytes_sec": 0,
                    "write_bytes_sec": 0,

                    # maximum throughput limit in bytes per second.
                    "read_bytes_sec_max": 0,
                    "write_bytes_sec_max": 0,

                    # maximum duration in seconds for the write_bytes_sec_max burst period.
                    # Only valid when the bytes_sec_max is set.
                    "read_bytes_sec_max_length": 0,
                    "write_bytes_sec_max_length": 0,

                    # I/O operations per second.
                    "read_iops_sec": 0,
                    "write_iops_sec": 0,

                    # maximum read I/O operations per second.
                    "write_iops_sec_max": 0,
                    "size_iops_sec": 0,

                    # maximum duration in seconds for the read_iops_sec_max burst period.
                    # Only valid when the iops_sec_max is set.
                    "read_iops_sec_max_length": 0,
                    "write_iops_sec_max_length": 0,
                },
                'allowed': {
                   'roles': ['admin'],
                   'categories': False,
                   'groups': False,
                   'users': False}
                }]).run())
            self.result(r.table('qos_disk').insert([{
                'id': 'limit50MBps',
                'name': 'BW:50MBps/IOPS:10K',
                'description': 'limit write and read to 50Mbps and IOPs to 10K',
                "iotune":{
                    # throughput limit in bytes per second.
                    "read_bytes_sec": 50 * 1e6,
                    "write_bytes_sec": 50 * 1e6,

                    # maximum throughput limit in bytes per second.
                    "read_bytes_sec_max": 0,
                    "write_bytes_sec_max": 0,

                    # maximum duration in seconds for the write_bytes_sec_max burst period.
                    # Only valid when the bytes_sec_max is set.
                    "read_bytes_sec_max_length": 0,
                    "write_bytes_sec_max_length": 0,

                    # I/O operations per second.
                    "read_iops_sec": 10 * 1e3,
                    "write_iops_sec": 10 * 1e3,

                    # maximum read I/O operations per second.
                    "write_iops_sec_max": 0,
                    "size_iops_sec": 0,

                    # maximum duration in seconds for the read_iops_sec_max burst period.
                    # Only valid when the iops_sec_max is set.
                    "read_iops_sec_max_length": 0,
                    "write_iops_sec_max_length": 0,
                },
                'allowed': {
                   'roles': ['admin'],
                   'categories': False,
                   'groups': False,
                   'users': False}
                }]).run())

    '''
    INTERFACE
    '''

    def interfaces(self):
        
            if not r.table_list().contains('interfaces').run():
                log.info("Table interfaces not found, creating and populating default network...")
                r.table_create('interfaces', primary_key="id").run()
                self.result(r.table('interfaces').insert([{'id': 'default',
                                                           'name': 'Default',
                                                           'description': 'Virtio isolated desktop network with dhcp',
                                                           'ifname': 'default',
                                                           'kind': 'network',
                                                           'model': 'virtio',
                                                           'net': 'default',
                                                           'qos_id': False,
                                                           'allowed': {
                                                               'roles': [],
                                                               'categories': [],
                                                               'groups': [],
                                                               'users': []}
                                                           }]).run())
                self.result(r.table('interfaces').insert([{'id': 'e1000_isolated',
                                                           'name': 'Intel PRO/1000 isolated',
                                                           'description': 'Compatible Intel PRO/1000 (e1000) isolated desktop network with dhcp',
                                                           'ifname': 'default',
                                                           'kind': 'network',
                                                           'model': 'e1000',
                                                           'net': 'default',
                                                           'qos_id': False,
                                                           'allowed': {
                                                               'roles': [],
                                                               'categories': [],
                                                               'groups': [],
                                                               'users': []}
                                                           }]).run()) 
                self.result(r.table('interfaces').insert([{'id': 'virtio_shared',
                                                           'name': 'Virtio shared',
                                                           'description': 'Virtio shared desktop network with dhcp.',
                                                           'ifname': 'shared',
                                                           'kind': 'network',
                                                           'model': 'virtio',
                                                           'net': 'shared',
                                                           'qos_id': False,
                                                           'allowed': {
                                                               'roles': ['admin'],
                                                               'categories': False,
                                                               'groups': False,
                                                               'users': False}
                                                           }]).run())
                for i in range(1,6):
                    self.result(r.table('interfaces').insert([{'id': 'private'+str(i),
                                                            'name': 'Private '+str(i),
                                                            'description': 'Private Virtio non isolated network without dhcp nor gateway',
                                                            'ifname': 'private'+str(i),
                                                            'kind': 'network',
                                                            'model': 'virtio',
                                                            'net': 'private'+str(i),
                                                            'qos_id': False,
                                                            'allowed': {
                                                                'roles': ['admin'],
                                                                'categories': False,
                                                                'groups': False,
                                                                'users': False}
                                                            }]).run())

            self.index_create('interfaces',['roles','categories','groups','users'])
            return True

    '''
    GRAPHICS
    '''

    def graphics(self):
        
            if not r.table_list().contains('graphics').run():
                log.info("Table graphics not found, creating and populating default network...")
                r.table_create('graphics', primary_key="id").run()
                self.result(r.table('graphics').insert([
                                                        {'id': 'default',
                                                         'name': 'Default',
                                                         'description': 'Spice viewer with compression and vlc',
                                                         'allowed': {
                                                             'roles': [],
                                                             'categories': [],
                                                             'groups': [],
                                                             'users': []},
                                                         'types': {'spice': {
                                                                            'options': {
                                                                                'image': {'compression': 'auto_glz'},
                                                                                'jpeg': {'compression': 'always'},
                                                                                'playback': {'compression': 'off'},
                                                                                'streaming': {'mode': 'all'},
                                                                                'zlib': {'compression': 'always'}},
                                                                            },
                                                                   'vlc':{
                                                                       'options':{}}
                                                                  },
                                                         }
                                                        ]).run())
            return True

    '''
    VIDEOS
    '''

    def videos(self):
        
            if not r.table_list().contains('videos').run():
                log.info("Table videos not found, creating and populating default network...")
                r.table_create('videos', primary_key="id").run()
                self.result(r.table('videos').insert([{'id': 'qxl32',
                                                       'name': 'QXL 32MB',
                                                       'description': 'QXL 32MB',
                                                       'ram': 32768,
                                                       'vram': 32768,
                                                       'model': 'qxl',
                                                       'heads': 1,
                                                       'allowed': {
                                                           'roles': ['admin'],
                                                           'categories': False,
                                                           'groups': False,
                                                           'users': False},
                                                       },
                                                       {'id': 'default',
                                                       'name': 'Default',
                                                       'description': 'Default video card',
                                                       'ram': 65536,
                                                       'vram': 65536,
                                                       'model': 'qxl',
                                                       'heads': 1,
                                                       'allowed': {
                                                           'roles': [],
                                                           'categories': [],
                                                           'groups': [],
                                                           'users': []},
                                                       },
                                                      {'id': 'vga',
                                                       'name': 'VGA',
                                                       'description': 'For old OSs',
                                                       'ram': 16384,
                                                       'vram': 16384,
                                                       'model': 'vga',
                                                       'heads': 1,
                                                       'allowed': {
                                                           'roles': ['admin'],
                                                           'categories': False,
                                                           'groups': False,
                                                           'users': False}
                                                       }
                                                       ]).run())
            return True

    '''
    BOOTS
    '''

    def boots(self):
        
        if not r.table_list().contains('boots').run():
            log.info("Table boots not found, creating and populating default network...")
            r.table_create('boots', primary_key="id").run()
            self.result(r.table('boots').insert([{'id': 'disk',
                                                  'name': 'Hard Disk',
                                                  'description': 'Boot based on hard disk list order',
                                                  'allowed': {
                                                      'roles': [],
                                                      'categories': [],
                                                      'groups': [],
                                                      'users': []}},
                                                 {'id': 'iso',
                                                  'name': 'CD/DVD',
                                                  'description': 'Boot based from ISO',
                                                  'allowed': {
                                                      'roles': ['admin'],
                                                      'categories': False,
                                                      'groups': False,
                                                      'users': False}},
                                                 {'id': 'pxe',
                                                  'name': 'PXE',
                                                  'description': 'Boot from network',
                                                  'allowed': {
                                                      'roles': ['admin'],
                                                      'categories': False,
                                                      'groups': False,
                                                      'users': False}},
                                                 {'id': 'floppy',
                                                  'name': 'Floppy',
                                                  'description': 'Boot from floppy disk',
                                                  'allowed': {
                                                      'roles': ['admin'],
                                                      'categories': False,
                                                      'groups': False,
                                                      'users': False}}                                                          
                                                 ]).run())
            return True

    '''
    DISKS
    '''

    def disks(self):
        
            if not r.table_list().contains('disks').run():
                log.info("Table disks not found, creating and populating default disk...")
                r.table_create('disks', primary_key="id").run()
                self.result(r.table('disks').insert([{'id': 'default',
                                                      'name': 'Default',
                                                      'description': 'Default',
                                                      "bus": "virtio",
                                                      "dev": "vda",
                                                      "type": "qcow2",
                                                      'allowed': {
                                                          'roles': [],
                                                          'categories': [],
                                                          'groups': [],
                                                          'users': []}}
                                                     ]).run())
            return True

    '''
    ISOS and FLOPPY:
    '''

    def media(self):
        
        if not r.table_list().contains('media').run():
            log.info("Table media not found, creating...")
            r.table_create('media', primary_key="id").run()
        self.index_create('media',['status','user','kind'])
        return True

    '''
    APPSCHEDULER JOBS:
    '''

    def scheduler_jobs(self):
        
        if not r.table_list().contains('scheduler_jobs').run():
            log.info("Table scheduler_jobs not found, creating...")
            r.table_create('scheduler_jobs', primary_key="id").run()
        return True

    '''
    HYPERVISORS
    '''

    def hypervisors(self):
        '''
        Read RethinkDB configuration from file
        '''
        if not r.table_list().contains('hypervisors').run():
            log.info("Table hypervisors not found, creating and populating with localhost")
            r.table_create('hypervisors', primary_key="id").run()
        rhyper = r.table('hypervisors')
        return self.result(rhyper.insert([{'id': 'isard-hypervisor',
                                         'hostname': 'isard-hypervisor',
                                         'viewer_hostname': 'localhost',
                                         'viewer_nat_hostname': 'localhost',
                                         'viewer_nat_offset': 0,
                                         'user': 'root',
                                         'port': '22',
                                         'uri': '',
                                         'capabilities': {'disk_operations': True,
                                                          'hypervisor': True},
                                         'hypervisors_pools': ['default'],
                                         'enabled': True,
                                         'status': 'Offline',
                                         'status_time': False,
                                         'prev_status': [],
                                         'detail': '',
                                         'description': 'Default hypervisor',
                                         'info': []},
                                        ]).run())  
        self.hypervisors_pools(disk_operations=[key])

    '''
    HYPERVISORS POOLS
    '''

    def hypervisors_pools(self,disk_operations=['isard-hypervisor']):
        
            if not r.table_list().contains('hypervisors_pools').run():
                log.info("Table hypervisors_pools not found, creating...")
                r.table_create('hypervisors_pools', primary_key="id").run()

                rpools = r.table('hypervisors_pools')

                #self.result(rpools.delete().run())
                cert = Certificates()
                viewer=cert.get_viewer()
                log.info("Table hypervisors_pools found, populating...")
                self.result(rpools.insert([{'id': 'default',
                                            'name': 'Default',
                                            'description': 'Non encrypted (not recommended)' if viewer is False else 'Encrypted viewer connections',
                                            'paths': {'bases':
                                                          [{'path':'/isard/bases',
                                                               'disk_operations': disk_operations, 'weight': 100}],
                                                      'groups':
                                                          [{'path':'/isard/groups',
                                                               'disk_operations': disk_operations, 'weight': 100}],
                                                      'templates':
                                                          [{'path':'/isard/templates',
                                                               'disk_operations': disk_operations, 'weight': 100}],
                                                      'media':
                                                          [{'path':'/isard/media',
                                                               'disk_operations': disk_operations, 'weight': 100}],
                                                      },
                                            'viewer':viewer,
                                            'interfaces': [],
                                            'cpu_host_model': 'host-passthrough',
                                            'allowed': {
                                                          'roles': [],
                                                          'categories': [],
                                                          'groups': [],
                                                          'users': []}
                                            }], conflict='update').run())
            return True

    '''
    HYPERVISORS_EVENTS
    '''

    def hypervisors_events(self):
        
            if not r.table_list().contains('hypervisors_events').run():
                log.info("Table hypervisors_events not found, creating...")
                r.table_create('hypervisors_events', primary_key="id").run()
            self.index_create('hypervisors_events',['domain','event','hyp_id'])
            return True

    '''
    HYPERVISORS_STATUS
    '''

    def hypervisors_status(self):
        
            if not r.table_list().contains('hypervisors_status').run():
                log.info("Table hypervisors_status not found, creating...")
                r.table_create('hypervisors_status', primary_key="id").run()
            self.index_create('hypervisors_status',['connected','hyp_id'])
            if not r.table_list().contains('hypervisors_status_history').run():
                log.info("Table hypervisors_status_history not found, creating...")
                r.table_create('hypervisors_status_history', primary_key="id").run()
            self.index_create('hypervisors_status_history',['connected','hyp_id'])
            return True

    '''
    DOMAINS
    '''

    def domains(self):
        
            if not r.table_list().contains('domains').run():
                log.info("Table domains not found, creating...")
                r.table_create('domains', primary_key="id").run()
            self.index_create('domains',['status','hyp_started','user','group','category','kind'])
            return True
            
    '''
    DOMAINS_STATUS
    '''

    def domains_status(self):
        
            if not r.table_list().contains('domains_status').run():
                log.info("Table domains_status not found, creating...")
                r.table_create('domains_status', primary_key="id").run()
            self.index_create('domains_status',['name','hyp_id'])
            if not r.table_list().contains('domains_status_history').run():
                log.info("Table domains_status_history not found, creating...")
                r.table_create('domains_status_history', primary_key="id").run()
            self.index_create('domains_status_history',['name','hyp_id'])
            return True
            
    '''
    DISK_OPERATIONS
    '''

    def disk_operations(self):
        
            if not r.table_list().contains('disk_operations').run():
                log.info("Table disk_operations not found, creating...")
                r.table_create('disk_operations', primary_key="id").run()
            return True

    
    '''
    HELPERS
    '''
    
    def result(self, res):
        if res['errors']:
            log.error(res['first_error'])
            exit(0)

    def _parseString(self, txt):
        import re, unicodedata, locale
        if type(txt) is not str:
            txt = txt.decode('utf-8')
        locale.setlocale(locale.LC_ALL, 'ca_ES')
        prog = re.compile("[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$", re.L)
        if not prog.match(txt):
            return False
        else:
            # ~ Replace accents
            txt = ''.join((c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn'))
            return txt.replace(" ", "_")




                                
    def _hypervisor_viewer_hostname(self,viewer_hostname):
        hostname_file='install/host_name'
        try:
            with open(hostname_file, "r") as hostFile:
                return hostFile.read().strip()
        except Exception as e:
            return viewer_hostname

        return 
        
    '''
    LOCATIONS
    '''

    def hosts_viewers(self):
        
            if not r.table_list().contains('hosts_viewers').run():
                log.info("Table hosts_viewers not found, creating...")
                r.table_create('hosts_viewers', primary_key="id").run()
                r.table('hosts_viewers').index_create("hostname").run()
                r.table('hosts_viewers').index_wait("hostname").run()
                r.table('hosts_viewers').index_create("mac").run()
                r.table('hosts_viewers').index_wait("mac").run()
                r.table('hosts_viewers').index_create("place_id").run()
                r.table('hosts_viewers').index_wait("place_id").run()
            self.index_create('hosts_viewers',['hostname','mac','place_id'])
            return True
            
    '''
    PLACES
    '''

    def places(self):
        
            if not r.table_list().contains('places').run():
                log.info("Table places not found, creating...")
                r.table_create('places', primary_key="id").run()
            self.index_create('places',['network','status'])
            return True



    '''
    BUILDER
    '''

    def builders(self):
        
            if not r.table_list().contains('builders').run():
                log.info("Table builders not found, creating...")
                r.table_create('builders', primary_key="id").run()
            return True


    '''
    VIRT BUILDER
    '''

    def virt_builder(self):
        
            if not r.table_list().contains('virt_builder').run():
                log.info("Table virt_builder not found, creating...")
                r.table_create('virt_builder', primary_key="id").run()
            return True

    '''
    VIRT INSTALL
    '''

    def virt_install(self):
            if not r.table_list().contains('virt_install').run():
                log.info("Table virt_install not found, creating...")
                r.table_create('virt_install', primary_key="id").run()
                self.result(r.table('virt_install').insert(self.update_virtinstalls()).run())
            return True

    def update_virtinstalls(self):
        from os import path
        from os import getcwd
        __location__ = path.realpath(
                        path.join(getcwd(), path.dirname(__file__)))
        f=open('./initdb/default_xmls/osinfo.txt')
        data = f.read()
        f.close()
        
        installs=[]
        for l in data.split('\n')[2:]:
            if l.find('|') > 1:
                v=[a.strip() for a in l.split('|')]
                xml=self.get_virtinstall_xml(v[0])
                if xml is not False:
                    icon=self.get_icon(v[1])               
                    installs.append({'id':v[0].strip(),
                                     'name':v[1].strip(),
                                     'vers':v[2].strip(),
                                     'www':v[3].strip(),
                                     'icon':icon,
                                     'xml':xml})
        return installs

    def get_virtinstall_xml(self,id):
        from os import listdir
        from os.path import isfile, join
        try:
            f=open('./initdb/default_xmls/'+id+'.xml')
            data = f.read()
            f.close()
        except:
            return False
        return data

    def get_icon(self,name):
        osname=name.replace('®','').split(' ')[0].lower()
        if 'win' in osname:                         icon='windows'
        elif 'rhel' in osname or 'rhl' in osname:   icon='redhat'
        elif 'alt' in osname or 'openbsd' in osname or 'netbsd' in osname:  icon='linux'
        elif 'suse' in osname: icon='opensuse'
        else:   icon=osname 
        return icon


    '''
    ENGINE
    '''

    def engine(self):
        
            if not r.table_list().contains('engine').run():
                log.info("Table engine not found, creating...")
                r.table_create('engine', primary_key="id").run()

                if r.table('engine').get('admin').run() is None:
                    self.result(r.table('engine').insert([{'id': 'engine',
                                                           'threads': {'changes':'on'},
                                                           'status_all_threads': 'on'
                                                           }]).run())


    def index_create(self,table,indexes):
        
            indexes_ontable=r.table(table).index_list().run()
            apply_indexes = [mi for mi in indexes if mi not in indexes_ontable]
            for i in apply_indexes:
                r.table(table).index_create(i).run()
                r.table(table).index_wait(i).run()

### disk_operations table not used anymore (delete if exists and remove creation)

    """ def enrollment_gen(self, length=6):
        chars = digits + ascii_lowercase
        dict = {}
        for key in ['manager','advanced','user']:
            code = False
            while code == False:
                code = "".join([random.choice(chars) for i in range(length)]) 
                if self.enrollment_code_check(code) == False:
                    dict[key]=code
                else:
                    code = False

        return dict  

    def enrollment_code_check(self, code):
        found=list(r.table('groups').filter({'enrollment':{'manager':code}}).run())
        if len(found) > 0:
            category = found[0]['id'].split('_')[0]
            return {'code':code,'role':'manager', 'category':category, 'group':found[0]['id']}
        found=list(r.table('groups').filter({'enrollment':{'advanced':code}}).run())
        if len(found) > 0:
            category = found[0]['id'].split('_')[0]
            return {'code':code,'role':'advanced', 'category':category, 'group':found[0]['id']}
        found=list(r.table('groups').filter({'enrollment':{'user':code}}).run())
        if len(found) > 0:
            category = found[0]['id'].split('_')[0]
            return {'code':code,'role':'user', 'category':category, 'group':found[0]['id']}  
        return False """  
