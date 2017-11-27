# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import rethinkdb as r
# Since no older versions than 0.9 are supported for Flask, this is safe
from flask import _app_ctx_stack as stack
from flask import current_app

from ..lib.log import *


class RethinkDB(object):

    def __init__(self, app=None, db=None):
        self.app = app
        self.db = db
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
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
        else:
            try:
                rcfg = configparser.ConfigParser()
                rcfg.read(os.path.join(os.path.dirname(__file__),'../config/isard.conf'))
            except Exception as e:
                log.info('Aborting. Please configure your RethinkDB database: config/isard.conf \n exception: {}'.format(e))
                sys.exit(0)
            
        app.config.setdefault('RETHINKDB_HOST', rcfg.get('RETHINKDB', 'HOST'))
        app.config.setdefault('RETHINKDB_PORT', rcfg.get('RETHINKDB', 'PORT'))
        app.config.setdefault('RETHINKDB_AUTH', '')
        app.config.setdefault('RETHINKDB_DB', rcfg.get('RETHINKDB', 'DBNAME'))

        @app.teardown_appcontext
        def teardown(exception):
            ctx = stack.top
            if hasattr(ctx, 'rethinkdb'):
                ctx.rethinkdb.close()

    def connect(self):
        return r.connect(host=current_app.config['RETHINKDB_HOST'],
                         port=current_app.config['RETHINKDB_PORT'],
                         auth_key=current_app.config['RETHINKDB_AUTH'],
                         db=self.db or current_app.config['RETHINKDB_DB'])

    @property
    def conn(self):
        ctx = stack.top
        if ctx is not None:
            if not hasattr(ctx, 'rethinkdb'):
                ctx.rethinkdb = self.connect()
            return ctx.rethinkdb
