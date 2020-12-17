# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

#~ from ..lib.log import *
#~ import logging as cfglog

import os,time
import traceback 

import rethinkdb as r

class loadConfig():

    def __init__(self, app=None):
        None
            
    def init_app(self, app):
        '''
        Read RethinkDB configuration from file
        '''
        try:
            app.config.setdefault('RETHINKDB_HOST', os.environ['WEBAPP_RETHINKDB_HOST'])
            app.config.setdefault('RETHINKDB_PORT', os.environ['WEBAPP_RETHINKDB_PORT'])
            app.config.setdefault('RETHINKDB_DB', os.environ['WEBAPP_RETHINKDB_DB'])
            app.config.setdefault('url', 'http://www.isardvdi.com:5050')

            app.config.setdefault('HOSTNAME', os.environ['HOSTNAME'])
            app.config.setdefault('TELEGRAM_BOT_TOKEN', os.environ['TELEGRAM_BOT_TOKEN'])
            app.config.setdefault('TELEGRAM_BOT_CHAT_ID', os.environ['TELEGRAM_BOT_CHAT_ID'])

            app.config.setdefault('LOG_LEVEL', os.environ['LOG_LEVEL'])
            app.debug=True if os.environ['LOG_LEVEL'] == 'DEBUG' else False
        except Exception as e:
            print('Loading environment vars failed')
            print(e)
            exit()

        print('Initial configuration loaded from environment vars')
        print('Using database connection {} and database {}'.format(app.config['RETHINKDB_HOST']+':'+app.config['RETHINKDB_PORT'],app.config['RETHINKDB_DB']))
        
        self.wait_for_db(app)
        return True

    def wait_for_db(self, app):
        ready=False
        while not ready:
            try:
                conn=r.connect(host=app.config['RETHINKDB_HOST'],
                            port=app.config['RETHINKDB_PORT'],
                            auth_key='',
                            db=app.config['RETHINKDB_DB'])
                print('Database server OK')
                ready=True
            except Exception as e:
                print(traceback.format_exc())
                print('Database server not present. Waiting to be ready')
                time.sleep(2)
        ready=False
        while not ready:
            try:
                tables = list(r.db('isard').table_list().run(conn))
            except:
                print('  No tables yet in database')
                time.sleep(1)
                continue
            if 'config' in tables: 
                ready=True
            else:
                print('Waiting for database to be populated with all tables...')
                print('   '+str(len(tables))+' populated')
                time.sleep(2)
        sysconfig = r.db('isard').table('config').get(1).run(conn)
        app.shares_templates = sysconfig.get('shares', {}).get('templates', False)
        app.shares_isos = sysconfig.get('shares', {}).get('isos', False)
        app.wireguard_keys = sysconfig.get('vpn', {}).get('wireguard', {}).get('keys', False)
            

def load_config():
        hyper={}
        try:
            hyper['isard-hypervisor']={'id': 'isard-hypervisor',
                        'hostname': 'isard-hypervisor',
                        'viewer_hostname': 'isard-hypervisor',
                        'user': 'root',
                        'port': '22',
                        'capabilities': {'disk_operations': True,
                                         'hypervisor': True},
                        'hypervisors_pools': ['default'],
                        'enabled': True}                                                     

            return {'RETHINKDB_HOST': os.environ['WEBAPP_RETHINKDB_HOST'],
                    'RETHINKDB_PORT': os.environ['WEBAPP_RETHINKDB_PORT'],
                    'RETHINKDB_DB':   os.environ['WEBAPP_RETHINKDB_DB'],
                    'HOSTNAME': os.environ['HOSTNAME'],
                    'TELEGRAM_BOT_TOKEN': os.environ['TELEGRAM_BOT_TOKEN'],
                    'TELEGRAM_BOT_CHAT_ID': os.environ['TELEGRAM_BOT_CHAT_ID'],
                    'LOG_LEVEL': os.environ['LOG_LEVEL'],
                    'url': 'http://www.isardvdi.com:5050',
#                    'LOG_FILE': rcfg.get('LOG', 'FILE'),
                    'DEFAULT_HYPERVISORS': hyper}
        except Exception as e:
            print('Error loading evironment variables. \n Exception: {}'.format(e))
            return False

