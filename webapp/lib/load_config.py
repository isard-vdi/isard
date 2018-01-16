# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

#~ from ..lib.log import *
#~ import logging as cfglog

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
        if not os.path.isfile(os.path.join(os.path.join(os.path.dirname(__file__),'../../isard.conf'))):
            try:
                print('isard.conf not found, trying to copy from isard.conf.default')
                # ~ shutil.copyfile('isard.conf.default', 'isard.conf') 
            except Exception as e:
                print('Aborting, isard.conf.default not found. Please configure your RethinkDB database in file isard.conf')
                print(str(e))
                return False

        try:
            rcfg = configparser.ConfigParser()
            rcfg.read(os.path.join(os.path.dirname(__file__),'../../isard.conf'))
        except Exception as e:
            print('isard.conf file can not be opened. \n Exception init_app: {}'.format(e))
            return False          
        app.config.setdefault('RETHINKDB_HOST', rcfg.get('RETHINKDB', 'HOST'))
        app.config.setdefault('RETHINKDB_PORT', rcfg.get('RETHINKDB', 'PORT'))
        app.config.setdefault('RETHINKDB_AUTH', '')
        app.config.setdefault('RETHINKDB_DB', rcfg.get('RETHINKDB', 'DBNAME'))
        
        app.config.setdefault('LOG_LEVEL', rcfg.get('LOG', 'LEVEL'))
        app.config.setdefault('LOG_FILE', rcfg.get('LOG', 'FILE'))
        app.debug=True if rcfg.get('LOG', 'LEVEL') == 'DEBUG' else False
        
        print('Initial configuration loaded from isard.conf.')
        print('Using database connection {} and database {}'.format(app.config['RETHINKDB_HOST']+':'+app.config['RETHINKDB_PORT'],app.config['RETHINKDB_DB']))
        return True


def load_config():

    #~ def __init__(self, app=None):
        #~ None
            
    #~ def init_app(self, app):
        '''
        Read RethinkDB configuration from file
        '''
        import configparser
        import os
        import shutil
        if not os.path.isfile(os.path.join(os.path.join(os.path.dirname(__file__),'../../isard.conf'))):
            try:
                print('isard.conf not found, trying to copy from isard.conf.default')
                # ~ shutil.copyfile('isard.conf.default', 'isard.conf') 
            except Exception as e:
                print('Aborting, isard.conf.default not found. Please configure your RethinkDB database in file isard.conf')
                print(str(e))
                return False

        try:
            rcfg = configparser.ConfigParser()
            rcfg.read(os.path.join(os.path.dirname(__file__),'../../isard.conf'))
        except Exception as e:
            print('isard.conf file can not be opened. \n Exception load_config: {}'.format(e))
            return False
        hyper={}
        try:
            for key,val in dict(rcfg.items('DEFAULT_HYPERVISORS')).items():
                vals=val.split(',')
                hyper[key]={'id': key,
                            'hostname': vals[0],
                            'viewer_hostname': vals[1],
                            'user': vals[2],
                            'port': vals[3],
                            'capabilities': {'disk_operations': True if int(vals[4]) else False,
                                             'hypervisor': True if int(vals[5]) else False},
                            'hypervisors_pools': [vals[6]],
                            'enabled': True if int(vals[7]) else False}                                                     

            return {'RETHINKDB_HOST': rcfg.get('RETHINKDB', 'HOST'),
                    'RETHINKDB_PORT': rcfg.get('RETHINKDB', 'PORT'),
                    'RETHINKDB_DB':   rcfg.get('RETHINKDB', 'DBNAME'),
                    'LOG_LEVEL': rcfg.get('LOG', 'LEVEL'),
                    'LOG_FILE': rcfg.get('LOG', 'FILE'),
                    'DEFAULT_HYPERVISORS': hyper}
        except Exception as e:
            print('isard.conf file can not be opened. \n Exception: {}'.format(e))
            return False
                        
        #~ print('Initial configuration loaded from isard.conf.')
        #~ print('Using database connection {} and database {}'.format(app.config['RETHINKDB_HOST']+':'+app.config['RETHINKDB_PORT'],app.config['RETHINKDB_DB']))
        #~ return True
