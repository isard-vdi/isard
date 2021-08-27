# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

#~ from ..lib.log import *
#~ import logging as cfglog

from api import app
# ~ import rethinkdb as r
#~ from flask import app

# ~ from .flask_rethink import RethinkDB
import os, sys, time, traceback
import logging as log

from rethinkdb import RethinkDB; r = RethinkDB()
#import rethinkdb as r

class loadConfig():

    def __init__(self, app=None):
        None
            
    def check_db(self):
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
                # print(traceback.format_exc())
                print('Database server '+app.config['RETHINKDB_HOST']+':'+app.config['RETHINKDB_PORT']+' not present. Waiting to be ready')
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
        r.db('isard').table('secrets').insert(
            {'id':'isardvdi',
            'secret': os.environ['API_ISARDVDI_SECRET'],
            'description': 'isardvdi',
            'domain': 'localhost',
            "category_id":"default",
            "role_id":"admin"}, conflict="replace"
        ).run(conn)
        r.db('isard').table('secrets').insert(
            {'id':'isardvdi-hypervisors',
            'secret': os.environ['API_HYPERVISORS_SECRET'],
            'description': 'isardvdi hypervisors access',
            'domain': '*',
            "category_id":"default",
            "role_id":"hypervisor"}, conflict="replace"
        ).run(conn)
    def init_app(self, app):
        '''
        Read RethinkDB configuration from environ
        '''     
        try:
            app.config.setdefault('RETHINKDB_HOST', os.environ['RETHINKDB_HOST'])
            app.config.setdefault('RETHINKDB_PORT', os.environ['RETHINKDB_PORT'])
            app.config.setdefault('RETHINKDB_AUTH', '')
            app.config.setdefault('RETHINKDB_DB', os.environ['RETHINKDB_DB'])
            
            app.config.setdefault('LOG_LEVEL', os.environ['LOG_LEVEL'])
            app.config.setdefault('LOG_FILE', 'isard-api.log')
            app.debug=True if os.environ['LOG_LEVEL'] == 'DEBUG' else False

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            log.error(exc_type, fname, exc_tb.tb_lineno)
            log.error('Missing parameters!')
            print('Missing parameters!')
            return False
        print('Initial configuration loaded...')
        self.check_db()
        return True
