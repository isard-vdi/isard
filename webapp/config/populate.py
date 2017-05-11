# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

#~ from pprint import pprint

import rethinkdb as r
import time
from webapp import app
from ..lib.flask_rethink import RethinkDB
from ..lib.log import *
db = RethinkDB(app)
db.init_app(app)

from ..auth.authentication import Password


class Populate(object):
    def __init__(self):
        p = Password()
        self.passwd = p.encrypt('isard')
        self.database()

    def defaults(self):
        log.info('Checking table roles')
        self.roles()
        log.info('Checking table categories')
        self.categories()
        log.info('Checking table groups')
        self.groups()
        log.info('Checking table users')
        self.users()
        log.info('Checking table hypervisors_pools')
        self.hypervisors_pools()
        log.info('Checking table hypervisors')
        self.hypervisors()
        log.info('Checking table interfaces')
        self.interfaces()
        log.info('Checking table graphics')
        self.graphics()
        log.info('Checking table videos')
        self.videos()
        log.info('Checking table disks')
        self.disks()
        log.info('Checking table domains')
        self.domains()
        log.info('Checking table domains_status')
        self.domains_status()
        log.info('Checking table domain_xmls')
        self.domains_xmls()
        log.info('Checking table isos')
        self.isos()
        log.info('Checking table boots')
        self.boots()
        log.info('Checking table hypervisors_events')
        self.hypervisors_events()
        log.info('Checking table hypervisors_status')
        self.hypervisors_status()
        log.info('Checking table disk_operations')
        self.disk_operations()
        log.info('Checking table disposables')
        self.disposables()
        log.info('Checking table backups')
        self.backups()
        log.info('Checking table config')
        self.config()

    '''
    DATABASE
    '''

    def database(self):
        try:
            with app.app_context():
                if not r.db_list().contains(app.config['RETHINKDB_DB']).run(db.conn):
                    log.warning('Database {} not found, creating new one.'.format(app.config['RETHINKDB_DB']))
                    self.result(r.db_create(app.config['RETHINKDB_DB']).run(db.conn))
                log.info('Database {} found.'.format(app.config['RETHINKDB_DB']))
                return True
        except Exception as e:
            log.error(e)
            return False

    '''
    CONFIG
    '''

    def config(self):
        with app.app_context():
            if not r.table_list().contains('config').run(db.conn):
                log.warning("Table config not found, creating new one.")
                r.table_create('config', primary_key='id').run(db.conn)
                self.result(r.table('config').insert([{'id': 1,
                                                       'auth': {'local': {'active': True},
                                                                'ldap': {'active': False,
                                                                         'ldap_server': 'ldap://ldap.domain.org',
                                                                         'bind_dn': 'dc=domain,dc=org'}},
                                                        'disposable_desktops':{'active': False},
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
                                                                            'log_level': 'DEBUG',
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
                                                                            },
                                                                    'carbon':{'active':False,'server':'','port':''}},
                                                        'version':0
                                                       }], conflict='error').run(db.conn))
                log.info("Table config populated with defaults.")
                return True
            else:
                return False

    '''
    DISPOSABLES
    '''

    def disposables(self):
        with app.app_context():
            if not r.table_list().contains('disposables').run(db.conn):
                log.info("Table disposables not found, creating and populating defaults...")
                r.table_create('disposables', primary_key="id").run(db.conn)
                self.result(r.table('disposables').insert([{'id': 'default',
                                                         'active': False,
                                                         'name': 'Default',
                                                         'description': 'Default disposable desktops',
                                                         'nets':[],
                                                         'disposables':[]  #{'id':'','name':'','description':''}
                                                         }]).run(db.conn))
                
            return True                

    '''
    BACKUPS
    '''

    def backups(self):
        with app.app_context():
            if not r.table_list().contains('backups').run(db.conn):
                log.info("Table backups not found, creating and populating defaults...")
                r.table_create('backups', primary_key="id").run(db.conn)
            return True                

    '''
    USERS
    Updated in Domains for
    '''

    def users(self):
        with app.app_context():
            if not r.table_list().contains('users').run(db.conn):
                log.info("Table users not found, creating...")
                r.table_create('users', primary_key="id").run(db.conn)
                r.table('users').index_create("group").run(db.conn)
                r.table('users').index_wait("group").run(db.conn)

                if r.table('users').get('admin').run(db.conn) is None:
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
                           'active': True,
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
                    self.result(r.table('users').insert(usr, conflict='update').run(db.conn))
                    log.info("  Inserted default admin username with password isard")
            return True

    '''
    ROLES
    '''

    def roles(self):
        with app.app_context():
            if not r.table_list().contains('roles').run(db.conn):
                log.info("Table roles not found, creating and populating...")
                r.table_create('roles', primary_key="id").run(db.conn)
                self.result(r.table('roles').insert([{'id': 'user',
                                                      'name': 'User',
                                                      'description': 'Can create desktops and start it',
                                                      'quota': {'domains': {'desktops': 3,
                                                                            'desktops_disk_max': 60000000,
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
                                                                            'desktops_disk_max': 90000000,
                                                                            'templates': 4,
                                                                            'templates_disk_max': 50000000,
                                                                            'running': 2,
                                                                            'isos': 3,
                                                                            'isos_disk_max': 3000000},
                                                                'hardware': {'vcpus': 3,
                                                                             'memory': 3000000}},  # 3GB
                                                      },
                                                     {'id': 'admin',
                                                      'name': 'Administrator',
                                                      'description': 'Is God',
                                                      'quota': {'domains': {'desktops': 12,
                                                                            'desktops_disk_max': 150000000,
                                                                            'templates': 8,
                                                                            'templates_disk_max': 150000000,
                                                                            'running': 4,
                                                                            'isos': 6,
                                                                            'isos_disk_max': 8000000},
                                                                'hardware': {'vcpus': 4,
                                                                             'memory': 4000000}}  # 10GB
                                                      }]).run(db.conn))
            return True

    '''
    CATEGORIES
    '''

    def categories(self):
        with app.app_context():
            if not r.table_list().contains('categories').run(db.conn):
                log.info("Table categories not found, creating...")
                r.table_create('categories', primary_key="id").run(db.conn)

                if r.table('categories').get('admin').run(db.conn) is None:
                    self.result(r.table('categories').insert([{'id': 'admin',
                                                               'name': 'Admin',
                                                               'description': 'Administrator',
                                                               'quota': r.table('roles').get('admin').run(db.conn)[
                                                                   'quota']
                                                               }]).run(db.conn))
                if r.table('categories').get('local').run(db.conn) is None:
                    self.result(r.table('categories').insert([{'id': 'local',
                                                               'name': 'Local',
                                                               'description': 'Local users',
                                                               'quota': r.table('roles').get('user').run(db.conn)[
                                                                   'quota']
                                                               }]).run(db.conn))
                if r.table('categories').get('disposables').run(db.conn) is None:
                    self.result(r.table('categories').insert([{'id': 'disposables',
                                                               'name': 'disposables',
                                                               'description': 'Disposable desktops',
                                                               'quota': r.table('roles').get('user').run(db.conn)[
                                                                   'quota']
                                                               }]).run(db.conn))
            return True

    '''
    GROUPS
    '''

    def groups(self):
        with app.app_context():
            if not r.table_list().contains('groups').run(db.conn):
                log.info("Table groups not found, creating...")
                r.table_create('groups', primary_key="id").run(db.conn)

                if r.table('groups').get('admin').run(db.conn) is None:
                    self.result(r.table('groups').insert([{'id': 'admin',
                                                           'name': 'admin',
                                                           'description': 'Administrator',
                                                           'quota': r.table('roles').get('admin').run(db.conn)['quota']
                                                           }]).run(db.conn))
                if r.table('groups').get('users').run(db.conn) is None:
                    self.result(r.table('groups').insert([{'id': 'local',
                                                           'name': 'local',
                                                           'description': 'Local users',
                                                           'quota': r.table('roles').get('user').run(db.conn)['quota']
                                                           }]).run(db.conn))

                if r.table('groups').get('advanced').run(db.conn) is None:
                    self.result(r.table('groups').insert([{'id': 'advanced',
                                                           'name': 'Advanced',
                                                           'description': 'Advanced users',
                                                           'quota': r.table('roles').get('advanced').run(db.conn)[
                                                               'quota']
                                                           }]).run(db.conn))
                if r.table('groups').get('disposables').run(db.conn) is None:
                    self.result(r.table('groups').insert([{'id': 'disposables',
                                                           'name': 'disposables',
                                                           'description': 'Disposable desktops',
                                                           'quota': r.table('roles').get('user').run(db.conn)[
                                                               'quota']
                                                           }]).run(db.conn))
        return True

    '''
    INTERFACE
    '''

    def interfaces(self):
        with app.app_context():
            if not r.table_list().contains('interfaces').run(db.conn):
                log.info("Table interfaces not found, creating and populating default network...")
                r.table_create('interfaces', primary_key="id").run(db.conn)
                r.table("interfaces").index_create("roles", multi=True).run(db.conn)
                r.table("interfaces").index_wait("roles").run(db.conn)
                r.table("interfaces").index_create("categories", multi=True).run(db.conn)
                r.table("interfaces").index_wait("categories").run(db.conn)
                r.table("interfaces").index_create("groups", multi=True).run(db.conn)
                r.table("interfaces").index_wait("groups").run(db.conn)
                r.table("interfaces").index_create("users", multi=True).run(db.conn)
                r.table("interfaces").index_wait("users").run(db.conn)
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
                                                           }]).run(db.conn))
            return True

    '''
    GRAPHICS
    '''

    def graphics(self):
        with app.app_context():
            if not r.table_list().contains('graphics').run(db.conn):
                log.info("Table graphics not found, creating and populating default network...")
                r.table_create('graphics', primary_key="id").run(db.conn)
                self.result(r.table('graphics').insert([{'id': 'default',
                                                         'name': 'Default',
                                                         'description': 'Spice viewer',
                                                         'type':'spice',
                                                         'allowed': {
                                                             'roles': [],
                                                             'categories': [],
                                                             'groups': [],
                                                             'users': []},
                                                         },
                                                        {'id': 'vnc',
                                                         'name': 'VNC',
                                                         'description': 'Not functional',
                                                         'type':'vnc',
                                                         'allowed': {
                                                             'roles': ['admin'],
                                                             'categories': False,
                                                             'groups': False,
                                                             'users': False}
                                                         }]).run(db.conn))
            return True

    '''
    VIDEOS
    '''

    def videos(self):
        with app.app_context():
            if not r.table_list().contains('videos').run(db.conn):
                log.info("Table videos not found, creating and populating default network...")
                r.table_create('videos', primary_key="id").run(db.conn)
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
                                                       }
                                                      #~ {'id': 'cirrus',
                                                       #~ 'name': 'Cirrus',
                                                       #~ 'description': 'Not functional',
                                                       #~ 'ram': 65536,
                                                       #~ 'vram': 65536,
                                                       #~ 'model': 'cirrus',
                                                       #~ 'heads': 1,
                                                       #~ 'allowed': {
                                                           #~ 'roles': ['admin'],
                                                           #~ 'categories': False,
                                                           #~ 'groups': False,
                                                           #~ 'users': False}
                                                       #~ }
                                                       ]).run(db.conn))
            return True

    '''
    BOOTS
    '''

    def boots(self):
        with app.app_context():
            if not r.table_list().contains('boots').run(db.conn):
                log.info("Table boots not found, creating and populating default network...")
                r.table_create('boots', primary_key="id").run(db.conn)
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
                                                          'users': False}}
                                                     ]).run(db.conn))
            return True

    '''
    DISKS
    '''

    def disks(self):
        with app.app_context():
            if not r.table_list().contains('disks').run(db.conn):
                log.info("Table disks not found, creating and populating default disk...")
                r.table_create('disks', primary_key="id").run(db.conn)
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
                                                     ]).run(db.conn))
            return True

    '''
    HYPERVISORS
    '''

    def hypervisors(self):

        with app.app_context():
            if not r.table_list().contains('hypervisors').run(db.conn):
                log.info("Table hypervisors not found, creating and populating with localhost")
                r.table_create('hypervisors', primary_key="id").run(db.conn)

                rhypers = r.table('hypervisors')
                log.info("Table hypervisors found, populating...")
                if rhypers.get('localhost').run(db.conn) is None and rhypers.count().run(db.conn) == 0:
                    self.result(rhypers.insert([{'id': 'localhost',
                                                 'hostname': '127.0.0.1',
                                                 'user': 'root',
                                                 'port': '22',
                                                 'uri': '',
                                                 'capabilities': {'disk_operations': True,
                                                                  'hypervisor': True},
                                                 'hypervisors_pools': ['default'],
                                                 'enabled': False,
                                                 'status': 'Offline',
                                                 'status_time': False,
                                                 'prev_status': [],
                                                 'detail': '',
                                                 'description': 'Embedded hypervisor',
                                                 'info': []},
                                                ]).run(db.conn))
            return True

    '''
    DOMAINS
    '''

    def domains(self):
        with app.app_context():
            if not r.table_list().contains('domains').run(db.conn):
                log.info("Table domains not found, creating...")
                r.table_create('domains', primary_key="id").run(db.conn)
                r.table('domains').index_create("status").run(db.conn)
                r.table('domains').index_wait("status").run(db.conn)
                r.table('domains').index_create("hyp_started").run(db.conn)
                r.table('domains').index_wait("hyp_started").run(db.conn)
                r.table('domains').index_create("user").run(db.conn)
                r.table('domains').index_wait("user").run(db.conn)
                r.table('domains').index_create("group").run(db.conn)
                r.table('domains').index_wait("group").run(db.conn)
                r.table('domains').index_create("category").run(db.conn)
                r.table('domains').index_wait("category").run(db.conn)
                r.table('domains').index_create("kind").run(db.conn)
                r.table('domains').index_wait("kind").run(db.conn)
            return True

    '''
    DOMAINS_XMLS: id name description xml 
    '''

    def domains_xmls(self):
        with app.app_context():
            if not r.table_list().contains('domains_xmls').run(db.conn):
                log.info("Table domains_xmls not found, creating...")
                r.table_create('domains_xmls', primary_key="id").run(db.conn)
        xml_path = './webapp/config/default_xmls/'
        xmls = os.listdir(xml_path)
        xmls_list = []
        for xml in xmls:
            if xml.endswith('.xml'):
                with open(xml_path + xml, "r") as xml_file:
                    xml_data = xml_file.read()
                xmls_list.append({'id': '_admin_' + xml.split('.')[0],
                                  'name': xml.split('.')[0],
                                  'description': 'File name: ' + xml,
                                  'xml': xml_data,
                                  'allowed': {'roles': ['admin'],
                                              'categories': False,
                                              'groups': False,
                                              'users': False}
                                  })
        with app.app_context():
            self.result(r.table('domains_xmls').insert(xmls_list, conflict='update').run(db.conn))
        return True

    '''
    ISOS: iso files
    '''

    def isos(self):
        with app.app_context():
            if not r.table_list().contains('isos').run(db.conn):
                log.info("Table isos not found, creating...")
                r.table_create('isos', primary_key="id").run(db.conn)
                r.table('isos').index_create("user").run(db.conn)
                r.table('isos').index_wait("user").run(db.conn)

        return True

    '''
    POOLS
    '''

    def hypervisors_pools(self):
        with app.app_context():
            if not r.table_list().contains('hypervisors_pools').run(db.conn):
                log.info("Table hypervisors_pools not found, creating...")
                r.table_create('hypervisors_pools', primary_key="id").run(db.conn)

                rpools = r.table('hypervisors_pools')

                self.result(rpools.delete().run(db.conn))
                log.info("Table hypervisors_pools found, populating...")
                self.result(rpools.insert([{'id': 'default',
                                            'name': 'Default',
                                            'description': 'Non encrypted (not recommended)',
                                            'paths': {'bases':
                                                          [{'path':'/isard/bases',
                                                               'disk_operations': ['localhost'], 'weight': 100}],
                                                      'groups':
                                                          [{'path':'/isard/groups',
                                                               'disk_operations': ['localhost'], 'weight': 100}],
                                                      'templates':
                                                          [{'path':'/isard/templates',
                                                               'disk_operations': ['localhost'], 'weight': 100}],
                                                      'disposables':
                                                          [{'path':'/isard/disposables',
                                                               'disk_operations': ['localhost'], 'weight': 100}],
                                                      'isos':
                                                          [{'path':'/isard/isos',
                                                               'disk_operations': ['localhost'], 'weight': 100}],
                                                      },
                                            'viewer':{'defaultMode':'Insecure',
                                                     'certificate':'',
                                                     'domain':''},
                                            'interfaces': [],
                                            'allowed': {
                                                          'roles': [],
                                                          'categories': [],
                                                          'groups': [],
                                                          'users': []}
                                            }], conflict='update').run(db.conn))
            return True

    '''
    HYPERVISORS_EVENTS
    '''

    def hypervisors_events(self):
        with app.app_context():
            if not r.table_list().contains('hypervisors_events').run(db.conn):
                log.info("Table hypervisors_events not found, creating...")
                r.table_create('hypervisors_events', primary_key="id").run(db.conn)
                r.table('hypervisors_events').index_create("domain").run(db.conn)
                r.table('hypervisors_events').index_wait("domain").run(db.conn)
                r.table('hypervisors_events').index_create("event").run(db.conn)
                r.table('hypervisors_events').index_wait("event").run(db.conn)
                r.table('hypervisors_events').index_create("hyp_id").run(db.conn)
                r.table('hypervisors_events').index_wait("hyp_id").run(db.conn)
            return True

    '''
    HYPERVISORS_STATUS
    '''

    def hypervisors_status(self):
        with app.app_context():
            if not r.table_list().contains('hypervisors_status').run(db.conn):
                log.info("Table hypervisors_status not found, creating...")
                r.table_create('hypervisors_status', primary_key="id").run(db.conn)
                r.table('hypervisors_status').index_create("connected").run(db.conn)
                r.table('hypervisors_status').index_wait("connected").run(db.conn)
                r.table('hypervisors_status').index_create("hyp_id").run(db.conn)
                r.table('hypervisors_status').index_wait("hyp_id").run(db.conn)
            if not r.table_list().contains('hypervisors_status_history').run(db.conn):
                log.info("Table hypervisors_status_history not found, creating...")
                r.table_create('hypervisors_status_history', primary_key="id").run(db.conn)
                r.table('hypervisors_status_history').index_create("connected").run(db.conn)
                r.table('hypervisors_status_history').index_wait("connected").run(db.conn)
                r.table('hypervisors_status_history').index_create("hyp_id").run(db.conn)
                r.table('hypervisors_status_history').index_wait("hyp_id").run(db.conn)
            return True
            
    '''
    DOMAINS_STATUS
    '''

    def domains_status(self):
        with app.app_context():
            if not r.table_list().contains('domains_status').run(db.conn):
                log.info("Table domains_status not found, creating...")
                r.table_create('domains_status', primary_key="id").run(db.conn)
                r.table('domains_status').index_create("name").run(db.conn)
                r.table('domains_status').index_wait("name").run(db.conn)
                r.table('domains_status').index_create("hyp_id").run(db.conn)
                r.table('domains_status').index_wait("hyp_id").run(db.conn)
            if not r.table_list().contains('domains_status_history').run(db.conn):
                log.info("Table domains_status_history not found, creating...")
                r.table_create('domains_status_history', primary_key="id").run(db.conn)
                r.table('domains_status_history').index_create("name").run(db.conn)
                r.table('domains_status_history').index_wait("name").run(db.conn)
                r.table('domains_status_history').index_create("hyp_id").run(db.conn)
                r.table('domains_status_history').index_wait("hyp_id").run(db.conn)
            return True
    '''
    DISK_OPERATIONS
    '''

    def disk_operations(self):
        with app.app_context():
            if not r.table_list().contains('disk_operations').run(db.conn):
                log.info("Table disk_operations not found, creating...")
                r.table_create('disk_operations', primary_key="id").run(db.conn)
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

    '''
    LOCATIONS
    '''

    def hosts_viewers(self):
        with app.app_context():
            if not r.table_list().contains('hosts_viewers').run(db.conn):
                log.info("Table hosts_viewers not found, creating...")
                r.table_create('hosts_viewers', primary_key="ip").run(db.conn)
                r.table('hosts_viewers').index_create("hostname").run(db.conn)
                r.table('hosts_viewers').index_wait("hostname").run(db.conn)
                r.table('hosts_viewers').index_create("mac").run(db.conn)
                r.table('hosts_viewers').index_wait("mac").run(db.conn)
                r.table('hosts_viewers').index_create("place_id").run(db.conn)
                r.table('hosts_viewers').index_wait("place_id").run(db.conn)
            return True
    '''
    PLACES
    '''

    def places(self):
        with app.app_context():
            if not r.table_list().contains('places').run(db.conn):
                log.info("Table places not found, creating...")
                r.table_create('places', primary_key="id").run(db.conn)
                r.table('places').index_create("network_address").run(db.conn)
                r.table('places').index_wait("network_address").run(db.conn)
                r.table('places').index_create("status").run(db.conn)
                r.table('places').index_wait("status").run(db.conn)
            return True
