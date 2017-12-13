# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

from ..lib.log import *

class loadConfig():

    def __init__(self, app=None):
        None
            
    def init_app(self, app):
        '''
        Read RethinkDB configuration from file
        '''
        import configparser
        import os
        import shutil
        if os.path.isfile(os.path.join(os.path.join(os.path.dirname(__file__),'../../isard.conf'))):
            try:
                rcfg = configparser.ConfigParser()
                rcfg.read(os.path.join(os.path.dirname(__file__),'../../isard.conf'))
            except Exception as e:
                log.error('isard.conf file can not be opened. \n Exception: {}'.format(e))
                return False
        else:
            try:
                log.warning('isard.conf not found, trying to copy from isard.conf.default')
                shutil.copyfile('isard.conf.default', 'isard.conf') 
            except Exception as e:
                log.error('Aborting, isard.conf.default not found. Please configure your RethinkDB database in file isard.conf')
                log.error(e)
                return False

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
        app.debug=True if rcfg.get('LOG', 'LEVEL') == 'DEBUG' else False
        log.info('Initial configuration loaded from isard.conf.')
        log.info('Using database connection {} and database {}'.format(app.config['RETHINKDB_HOST']+':'+app.config['RETHINKDB_PORT'],app.config['RETHINKDB_DB']))
        return True
