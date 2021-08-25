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
#~ from flask import current_app

# ~ from .flask_rethink import RethinkDB
import os, sys
import logging as log

class loadConfig():

    def __init__(self, app=None):
        None
            
    def check_db(self):
        return True
        try:
            conn=RethinkDB(None)
            conn.connect()
            return True
        except Exception as e:
            print(e)
            return False
            
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
        if self.check_db() is False:
            print('No database found!!!!!!!!!!')
            print('Using database connection {} and database {}'.format(app.config['RETHINKDB_HOST']+':'+app.config['RETHINKDB_PORT'],app.config['RETHINKDB_DB']))
            return False
        return True
