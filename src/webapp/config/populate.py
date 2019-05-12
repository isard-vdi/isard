# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import rethinkdb as r
import time, sys

from ..lib.log import *
from ..auth.authentication import Password
from ..lib.load_config import load_config
from ..lib.admin_api import Certificates

class Populate(object):
    def __init__(self,dreg):
        self.register_code=dreg['resources']['code']
        self.register_url=dreg['resources']['url']
        self.cfg=load_config()
        try:
            self.conn = r.connect( self.cfg['RETHINKDB_HOST'],self.cfg['RETHINKDB_PORT'],self.cfg['RETHINKDB_DB']).repl()
        except Exception as e:
            None
        self.p = Password()
        self.passwd = self.p.encrypt('isard')
        
    '''
    DATABASE
    '''

    def database(self):
        try:
                if not r.db_list().contains(self.cfg['RETHINKDB_DB']).run():
                    log.warning('Database {} not found, creating new one.'.format(self.cfg['RETHINKDB_DB']))
                    r.db_create(self.cfg['RETHINKDB_DB']).run()
                    return 1
                log.info('Database {} found.'.format(self.cfg['RETHINKDB_DB']))
                return 2
        except Exception as e:
            #~ exc_type, exc_obj, exc_tb = sys.exc_info()
            #~ fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            #~ log.error(exc_type, fname, exc_tb.tb_lineno)
            log.error('Can not connect to rethinkdb database! Is it running on HOST:'+self.cfg['RETHINKDB_HOST']+' PORT:'+self.cfg['RETHINKDB_PORT']+' DB:'+self.cfg['RETHINKDB_DB']+' ??')
            return False


    def defaults(self):
        return self.check_integrity()

    def check_integrity(self,commit=False):
        dbtables=r.table_list().run()
        newtables=['roles','categories','groups','users','vouchers',
                'hypervisors','hypervisors_pools','interfaces',
                'graphics','videos','disks','domains','domains_status','domains_status_history',
                'virt_builder','virt_install','builders','media',
                'boots','hypervisors_events','hypervisors_status','hypervisors_status_history',
                'disk_operations','hosts_viewers','places','disposables','eval_results',
                'scheduler_jobs','backups','config','engine']
        tables_to_create=list(set(newtables) - set(dbtables))
        d = {k:v for v,k in enumerate(newtables)}
        tables_to_create.sort(key=d.get)
        tables_to_delete=list(set(dbtables) - set(newtables))
        print(tables_to_create)
        if not commit:
            return {'tables_to_create':tables_to_create,'tables_to_delete':tables_to_delete}
        else:
            for t in tables_to_create:
                table=t
                if table.startswith('hypervisors_status'): table='hypervisors_status'
                if table.startswith('domains_status'): table='domains_status'
                log.info('Creating new table: '+t)
                log.info('  Result: '+str(eval('self.'+table+'()')))
            for t in tables_to_delete:
                log.info('Deleting old table: '+t)
                log.info('  Result: '+str(r.table_drop(t).run()))
        return True

    '''
    CONFIG
    '''

    def config(self):
        with app.app_context():
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
                                                        'resources': {'code':self.register_code,
                                                                    'url':self.register_url}
                                                       }], conflict='update').run())
                log.info("Table config populated with defaults.")
                return True
            else:
                return False

    '''
    DISPOSABLES
    '''

    def disposables(self):
        with app.app_context():
            if not r.table_list().contains('disposables').run():
                log.info("Table disposables not found, creating and populating defaults...")
                r.table_create('disposables', primary_key="id").run()
                self.result(r.table('disposables').insert([{'id': 'default',
                                                         'active': False,
                                                         'name': 'Default',
                                                         'description': 'Default disposable desktops',
                                                         'nets':[],
                                                         'disposables':[]  #{'id':'','name':'','description':''}
                                                         }]).run())
                
            return True                

    '''
    BACKUPS
    '''

    def backups(self):
        with app.app_context():
            if not r.table_list().contains('backups').run():
                log.info("Table backups not found, creating and populating defaults...")
                r.table_create('backups', primary_key="id").run()
            return True                

    '''
    USERS
    Updated in Domains for
    '''

    def users(self):
        with app.app_context():
            if not r.table_list().contains('users').run():
                log.info("Table users not found, creating...")
                r.table_create('users', primary_key="id").run()

                if r.table('users').get('admin').run() is None:
                    usr = [{'id': 'admin',
                           'name': 'Administrator',
                           'kind': 'local',
                           'active': True,
                           'accessed': time.time(),
                           'username': 'admin',
                           'password': self.passwd,
                           'role': 'admin',
                           'category': 'admin',
                           'group': 'admin',
                           'mail': 'admin@isard.io',
                           'quota': {'domains': {'desktops': 99,
                                                 'desktops_disk_max': 999999999,  # 1TB
                                                 'templates': 99,
                                                 'templates_disk_max': 999999999,
                                                 'running': 99,
                                                 'isos': 99,
                                                 'isos_disk_max': 999999999},
                                     'hardware': {'vcpus': 8,
                                                  'memory': 20000000}},  # 10GB
                           },
                          {'id': 'disposable',
                           'name': 'Disposable',
                           'kind': 'local',
                           'active': False,
                           'accessed': time.time(),
                           'username': 'disposable',
                           'password': self.passwd,
                           'role': 'user',
                           'category': 'disposables',
                           'group': 'disposables',
                           'mail': '',
                           'quota': {'domains': {'desktops': 99,
                                                 'desktops_disk_max': 999999999,  # 1TB
                                                 'templates': 99,
                                                 'templates_disk_max': 999999999,
                                                 'running': 99,
                                                 'isos': 99,
                                                 'isos_disk_max': 999999999},
                                     'hardware': {'vcpus': 8,
                                                  'memory': 20000000}},  # 10GB
                           }
                           ]
                    self.result(r.table('users').insert(usr, conflict='update').run())
                    log.info("  Inserted default admin username with password isard")
                if r.table('users').get('eval').run() is None:
                    usr = [{'id': 'eval',
                            'name': 'Evaluator',
                            'kind': 'local',
                            'active': False,
                            'accessed': time.time(),
                            'username': 'eval',
                            'password': self.p.generate_human(8),
                            'role': 'admin',
                            'category': 'admin',
                            'group': 'eval',
                            'mail': 'eval@isard.io',
                            'quota': {'domains': {'desktops': 99,
                                                  'desktops_disk_max': 999999999,  # 1TB
                                                  'templates': 99,
                                                  'templates_disk_max': 999999999,
                                                  'running': 99,
                                                  'isos': 99,
                                                  'isos_disk_max': 999999999},
                                      'hardware': {'vcpus': 8,
                                                   'memory': 20000000}},  # 10GB
                            },
                           ]
                    self.result(r.table('users').insert(usr, conflict='update').run())
                    log.info("  Inserted default eval username with random password")
            self.index_create('users',['group'])
            return True

    '''
    VOUCHERS
    Grant access on new voucher
    '''

    def vouchers(self):
        with app.app_context():
            if not r.table_list().contains('vouchers').run():
                log.info("Table vouchers not found, creating...")
                r.table_create('vouchers', primary_key="id").run()
            return True


    '''
    ROLES
    '''

    def roles(self):
        with app.app_context():
            if not r.table_list().contains('roles').run():
                log.info("Table roles not found, creating and populating...")
                r.table_create('roles', primary_key="id").run()
                self.result(r.table('roles').insert([{'id': 'user',
                                                      'name': 'User',
                                                      'description': 'Can create desktops and start it',
                                                      'quota': {'domains': {'desktops': 3,
                                                                            'desktops_disk_max': 25000000,
                                                                            'templates': 0,
                                                                            'templates_disk_max': 0,
                                                                            'running': 1,
                                                                            'isos': 0,
                                                                            'isos_disk_max': 0},
                                                                'hardware': {'vcpus': 2,
                                                                             'memory': 2500000}},  # 2,5GB
                                                      },
                                                     {'id': 'advanced',
                                                      'name': 'Advanced user',
                                                      'description': 'Can create desktops and templates and start desktops',
                                                      'quota': {'domains': {'desktops': 6,
                                                                            'desktops_disk_max': 40000000,
                                                                            'templates': 4,
                                                                            'templates_disk_max': 40000000,
                                                                            'running': 2,
                                                                            'isos': 3,
                                                                            'isos_disk_max': 5000000},
                                                                'hardware': {'vcpus': 3,
                                                                             'memory': 3000000}},  # 3GB
                                                      },
                                                     {'id': 'admin',
                                                      'name': 'Administrator',
                                                      'description': 'Is God',
                                                      'quota': {'domains': {'desktops': 12,
                                                                            'desktops_disk_max': 350000000,
                                                                            'templates': 8,
                                                                            'templates_disk_max': 350000000,
                                                                            'running': 4,
                                                                            'isos': 6,
                                                                            'isos_disk_max': 15000000},
                                                                'hardware': {'vcpus': 4,
                                                                             'memory': 4000000}}  # 10GB
                                                      }]).run())
            return True

    '''
    CATEGORIES
    '''

    def categories(self):
        with app.app_context():
            if not r.table_list().contains('categories').run():
                log.info("Table categories not found, creating...")
                r.table_create('categories', primary_key="id").run()

                if r.table('categories').get('admin').run() is None:
                    self.result(r.table('categories').insert([{'id': 'admin',
                                                               'name': 'Admin',
                                                               'description': 'Administrator',
                                                               'quota': r.table('roles').get('admin').run()[
                                                                   'quota']
                                                               }]).run())
                if r.table('categories').get('local').run() is None:
                    self.result(r.table('categories').insert([{'id': 'local',
                                                               'name': 'Local',
                                                               'description': 'Local users',
                                                               'quota': r.table('roles').get('user').run()[
                                                                   'quota']
                                                               }]).run())
                if r.table('categories').get('disposables').run() is None:
                    self.result(r.table('categories').insert([{'id': 'disposables',
                                                               'name': 'disposables',
                                                               'description': 'Disposable desktops',
                                                               'quota': r.table('roles').get('user').run()[
                                                                   'quota']
                                                               }]).run())
            return True

    '''
    GROUPS
    '''

    def groups(self):
        with app.app_context():
            if not r.table_list().contains('groups').run():
                log.info("Table groups not found, creating...")
                r.table_create('groups', primary_key="id").run()

                if r.table('groups').get('admin').run() is None:
                    self.result(r.table('groups').insert([{'id': 'admin',
                                                           'name': 'Admin',
                                                           'description': 'Administrator',
                                                           'quota': r.table('roles').get('admin').run()['quota']
                                                           }]).run())
                if r.table('groups').get('users').run() is None:
                    self.result(r.table('groups').insert([{'id': 'local',
                                                           'name': 'Local',
                                                           'description': 'Local users',
                                                           'quota': r.table('roles').get('user').run()['quota']
                                                           }]).run())

                if r.table('groups').get('advanced').run() is None:
                    self.result(r.table('groups').insert([{'id': 'advanced',
                                                           'name': 'Advanced',
                                                           'description': 'Advanced users',
                                                           'quota': r.table('roles').get('advanced').run()[
                                                               'quota']
                                                           }]).run())
                if r.table('groups').get('disposables').run() is None:
                    self.result(r.table('groups').insert([{'id': 'disposables',
                                                           'name': 'Disposables',
                                                           'description': 'Disposable desktops',
                                                           'quota': r.table('roles').get('user').run()[
                                                               'quota']
                                                           }]).run())
            if r.table('groups').get('eval').run() is None:
                self.result(r.table('groups').insert([{'id': 'eval',
                                                       'name': 'Eval',
                                                       'description': 'Evaluator',
                                                       'quota': r.table('roles').get('admin').run()['quota']
                                                       }]).run())
        return True

    '''
    INTERFACE
    '''

    def interfaces(self):
        with app.app_context():
            if not r.table_list().contains('interfaces').run():
                log.info("Table interfaces not found, creating and populating default network...")
                r.table_create('interfaces', primary_key="id").run()
                self.result(r.table('interfaces').insert([{'id': 'default',
                                                           'name': 'Default',
                                                           'description': 'Default network',
                                                           'ifname': 'default',
                                                           'kind': 'network',
                                                           'model': 'virtio',
                                                           'net': '',
                                                           'allowed': {
                                                               'roles': [],
                                                               'categories': [],
                                                               'groups': [],
                                                               'users': []}
                                                           }]).run())
            self.index_create('interfaces',['roles','categories','groups','users'])
            return True

    '''
    GRAPHICS
    '''

    def graphics(self):
        with app.app_context():
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
        with app.app_context():
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
        with app.app_context():
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
        with app.app_context():
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
        with app.app_context():
            if not r.table_list().contains('media').run():
                log.info("Table media not found, creating...")
                r.table_create('media', primary_key="id").run()
        self.index_create('media',['status','user','kind'])
        return True

    '''
    APPSCHEDULER JOBS:
    '''

    def scheduler_jobs(self):
        with app.app_context():
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
        import configparser
        import os
        if os.path.isfile(os.path.join(os.path.join(os.path.dirname(__file__),'../../isard.conf'))):
            try:
                rcfg = configparser.ConfigParser()
                rcfg.read(os.path.join(os.path.dirname(__file__),'../../isard.conf'))
            except Exception as e:
                log.info('isard.conf file can not be opened. \n Exception: {}'.format(e))
                sys.exit(0)
        
        with app.app_context():
            if not r.table_list().contains('hypervisors').run():
                log.info("Table hypervisors not found, creating and populating with localhost")
                r.table_create('hypervisors', primary_key="id").run()

                rhypers = r.table('hypervisors')
                log.info("Table hypervisors found, populating...")
                if rhypers.count().run() == 0:
                    for key,val in dict(rcfg.items('DEFAULT_HYPERVISORS')).items():
                        vals=val.split(',')
                        self.result(rhypers.insert([{'id': key,
                                                     'hostname': vals[0],
                                                     'viewer_hostname': self._hypervisor_viewer_hostname(vals[1]),
                                                     'viewer_nat_hostname': self._hypervisor_viewer_hostname(vals[1]),
                                                     'viewer_nat_offset': 0,
                                                     'user': vals[2],
                                                     'port': vals[3],
                                                     'uri': '',
                                                     'capabilities': {'disk_operations': True if int(vals[4]) else False,
                                                                      'hypervisor': True if int(vals[5]) else False},
                                                     'hypervisors_pools': [vals[6]],
                                                     'enabled': True if int(vals[7]) else False,
                                                     'status': 'Offline',
                                                     'status_time': False,
                                                     'prev_status': [],
                                                     'detail': '',
                                                     'description': 'Default hypervisor',
                                                     'info': []},
                                                    ]).run())  
                    self.hypervisors_pools(disk_operations=[key])
        return True

    '''
    HYPERVISORS POOLS
    '''

    def hypervisors_pools(self,disk_operations=['localhost']):
        with app.app_context():
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
                                                      'disposables':
                                                          [{'path':'/isard/disposables',
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
        with app.app_context():
            if not r.table_list().contains('hypervisors_events').run():
                log.info("Table hypervisors_events not found, creating...")
                r.table_create('hypervisors_events', primary_key="id").run()
            self.index_create('hypervisors_events',['domain','event','hyp_id'])
            return True

    '''
    HYPERVISORS_STATUS
    '''

    def hypervisors_status(self):
        with app.app_context():
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
        with app.app_context():
            if not r.table_list().contains('domains').run():
                log.info("Table domains not found, creating...")
                r.table_create('domains', primary_key="id").run()
            self.index_create('domains',['status','hyp_started','user','group','category','kind'])
            return True
            
    '''
    DOMAINS_STATUS
    '''

    def domains_status(self):
        with app.app_context():
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
        with app.app_context():
            if not r.table_list().contains('disk_operations').run():
                log.info("Table disk_operations not found, creating...")
                r.table_create('disk_operations', primary_key="id").run()
            return True

    '''
        EVAL
    '''

    def eval_results(self):
        with app.app_context():
            if not r.table_list().contains('eval_results').run():
                log.info("Table eval_results not found, creating...")
                r.table_create('eval_results', primary_key="id").run()
                # code --> Identify group of eval results.
                # This group of results was taken over the same pool and hypervisors characteristics.
                # Example: code: A
            self.index_create('eval_results',['code'])

            if not r.table_list().contains('eval_initial_ux').run():
                log.info("Table eval_initial_ux not found, creating...")
                r.table_create('eval_initial_ux', primary_key="id").run()
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
        with app.app_context():
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
        with app.app_context():
            if not r.table_list().contains('places').run():
                log.info("Table places not found, creating...")
                r.table_create('places', primary_key="id").run()
            self.index_create('places',['network','status'])
            return True



    '''
    BUILDER
    '''

    def builders(self):
        with app.app_context():
            if not r.table_list().contains('builders').run():
                log.info("Table builders not found, creating...")
                r.table_create('builders', primary_key="id").run()
            return True


    '''
    VIRT BUILDER
    '''

    def virt_builder(self):
        with app.app_context():
            if not r.table_list().contains('virt_builder').run():
                log.info("Table virt_builder not found, creating...")
                r.table_create('virt_builder', primary_key="id").run()
            return True

    '''
    VIRT INSTALL
    '''

    def virt_install(self):
        with app.app_context():
            if not r.table_list().contains('virt_install').run():
                log.info("Table virt_install not found, creating...")
                r.table_create('virt_install', primary_key="id").run()
            return True



    # ~ ''''

    # ~ VIRT - BUILDER
    # ~ VIRT - INSTALL

    # ~ '''


    # ~ def create_builders(self):
        # ~ l=[]
        # ~ d_fedora25 = {'id': 'fedora25_gnome_office',
                      # ~ 'name': 'Fedora 25 with gnome and libre office',
                      # ~ 'builder':{
                          # ~ 'id': 'fedora-25',
                          # ~ 'options':
    # ~ """--update
    # ~ --selinux-relabel
    # ~ --install "@workstation-product-environment"
    # ~ --install "inkscape,tmux,@libreoffice,chromium"
    # ~ --install "libreoffice-langpack-ca,langpacks-es"
    # ~ --root-password password:isard
    # ~ --link /usr/lib/systemd/system/graphical.target:/etc/systemd/system/default.target
    # ~ --firstboot-command 'localectl set-locale LANG=es_ES.utf8'
    # ~ --firstboot-command 'localectl set-keymap es'
    # ~ --firstboot-command 'systemctl isolate graphical.target'
    # ~ --firstboot-command 'useradd -m -p "" isard ; chage -d 0 isard'
    # ~ --hostname 'isard-fedora'"""
                      # ~ },
                      # ~ 'install':{
                          # ~ 'id': 'fedora25',
                          # ~ 'options': ''
                      # ~ }
                      # ~ }
        # ~ l.append(d_fedora25)
        
        # ~ d_debian8 = {'id': 'debian8_gnome_office',
                      # ~ 'name': 'Debian 8 with gnome and libre office',
                      # ~ 'builder':{
                          # ~ 'id': 'debian-8',
                          # ~ 'options':
    # ~ """--update
    # ~ --selinux-relabel
    # ~ --install 'xfce4,locales,ibus'
    # ~ --install 'gdm3,libreoffice,libreoffice-l10n-es'
    # ~ --install 'inkscape,tmux,chromium'
    # ~ --edit '/etc/default/keyboard: s/^XKBLAYOUT=.*/XKBLAYOUT="es"/'
    # ~ --write '/etc/default/locale:LANG="es_ES.UTF-8"'
    # ~ --run-command "locale-gen"
    # ~ --root-password password:isard
    # ~ --firstboot-command 'useradd -m -p "" isard ; chage -d 0 isard'
    # ~ --hostname 'isard-debian'"""
                      # ~ },
                      # ~ 'install':{
                          # ~ 'id': 'debian8',
                          # ~ 'options': ''
                      # ~ }
                      # ~ }
        # ~ l.append(d_debian8)
        
        # ~ d_ubuntu1604 = {'id': 'ubuntu1604_gnome_office',
                      # ~ 'name': 'Ubuntu 16.04 with gnome and libre office',
                      # ~ 'builder':{
                          # ~ 'id': 'ubuntu-16.04',
                          # ~ 'options':
    # ~ """--update
    # ~ --selinux-relabel
    # ~ --install "ubuntu-desktop"
    # ~ --install "inkscape,tmux,libreoffice,chromium-bsu"
    # ~ --install 'language-pack-es-base,language-pack-es'
    # ~ --edit '/etc/default/keyboard: s/^XKBLAYOUT=.*/XKBLAYOUT="es"/'
    # ~ --write '/etc/default/locale:LANG="es_ES.UTF-8"'
    # ~ --run-command "locale-gen"
    # ~ --root-password password:isard
    # ~ --link /usr/lib/systemd/system/graphical.target:/etc/systemd/system/default.target
    # ~ --firstboot-command 'systemctl isolate graphical.target'
    # ~ --hostname 'isard-ubuntu'"""
                      # ~ },
                      # ~ 'install':{
                          # ~ 'id': 'ubuntu16',
                          # ~ 'options': ''
                      # ~ }
                      # ~ }
        # ~ l.append(d_ubuntu1604)

        # ~ d_cirros_35 = {'id': 'cirros35',
                      # ~ 'name': 'CirrOS 3.5',
                      # ~ 'builder':{
                          # ~ 'id': 'cirros-0.3.5',
                          # ~ 'options':
    # ~ """"""
                      # ~ },
                      # ~ 'install':{
                          # ~ 'id': 'centos7.0',
                          # ~ 'options': ''
                      # ~ }
                      # ~ }
        # ~ l.append(d_cirros_35)
        
        # ~ return l

    # ~ def update_virtbuilder(self,url="http://libguestfs.org/download/builder/index"):

        # ~ import urllib.request
        # ~ with urllib.request.urlopen(url) as response:
            # ~ f = response.read()

        # ~ s = f.decode('utf-8')
        # ~ #select only arch x86_64
        # ~ l = [a.split(']') for a in s[1:].split('\n[') if a.find('\narch=x86_64') > 0]

        # ~ list_virtbuilder = []
        # ~ for b in l:
            # ~ d = {a.split('=')[0]: a.split('=')[1] for a in b[1].split('notes')[0].split('\n')[1:] if
                       # ~ len(a) > 0 and a.find('=') > 0}
            # ~ d['id'] = b[0]
            # ~ list_virtbuilder.append(d)

        # ~ return list_virtbuilder


    # ~ def update_virtinstall(self,from_osinfo_query=False):

        # ~ if from_osinfo_query is True:
            # ~ import subprocess
            # ~ data = subprocess.getoutput("osinfo-query os")

        # ~ else:
            # ~ from os import path
            # ~ from os import getcwd
            # ~ __location__ = path.realpath(
                    # ~ path.join(getcwd(), path.dirname(__file__)))
            # ~ f=open(__location__+'/osinfo.txt')
            # ~ data = f.read()
            # ~ f.close()

        # ~ installs=[]

        # ~ for l in data.split('\n')[2:]:
            # ~ if l.find('|') > 1:

                # ~ v=[a.strip() for a in l.split('|')]

                # ~ #DEFAULT FONT
                # ~ font_type = 'font-awesome'
                # ~ font_class = 'fa-linux'

                # ~ for oslinux in ('fedora,centos,debian,freebsd,mageia,mandriva,opensuse,ubuntu,opensuse'.split(',')):
                        # ~ font_type  = 'font-linux'
                        # ~ font_class = 'fl-'+oslinux

                # ~ if v[0].find('rhel') == 0 or v[0].find('rhl') == 0:
                    # ~ font_type  = 'font-linux'
                    # ~ font_class = 'fl-redhat'

                # ~ elif v[0].find('win') == 0:
                    # ~ font_type  = 'font-awesome'
                    # ~ font_class = 'fa-windows'

                # ~ installs.append({'id':v[0].strip(),
                                 # ~ 'name':v[1].strip(),
                                 # ~ 'vers':v[2].strip(),
                                 # ~ 'www':v[3].strip(),
                                 # ~ 'font_type':font_type,
                                 # ~ 'icon':font_class})

        # ~ return installs
    
    '''
    ENGINE
    '''

    def engine(self):
        with app.app_context():
            if not r.table_list().contains('engine').run():
                log.info("Table engine not found, creating...")
                r.table_create('engine', primary_key="id").run()

                if r.table('engine').get('admin').run() is None:
                    self.result(r.table('engine').insert([{'id': 'engine',
                                                           'threads': {'changes':'on'},
                                                           'status_all_threads': 'on'
                                                           }]).run())


    def index_create(self,table,indexes):
        with app.app_context():
            indexes_ontable=r.table(table).index_list().run()
            apply_indexes = [mi for mi in indexes if mi not in indexes_ontable]
            for i in apply_indexes:
                r.table(table).index_create(i).run()
                r.table(table).index_wait(i).run()

### disk_operations table not used anymore (delete if exists and remove creation)
