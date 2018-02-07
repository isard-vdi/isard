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


release_version = 1



tables=['config']

class Upgrade(object):
    def __init__(self):
        
        # ~ self.rele = 9
        
        self.conf=load_config()
        
        self.conn=False
        self.cfg=False
        try:
            self.conn = r.connect( self.conf['RETHINKDB_HOST'],self.conf['RETHINKDB_PORT'],self.conf['RETHINKDB_DB']).repl()
        except Exception as e:
            print(e)
            self.conn=False

        if self.conn is not False and r.db_list().contains(self.conf['RETHINKDB_DB']).run():
            if r.table_list().contains('config').run():
                self.cfg = r.table('config').get(1).run()
                log.info('Your actual database version is: '+str(self.cfg['version']))
                if release_version > self.cfg['version']:
                    log.warning('Database upgrade needed! You have version '+str(self.cfg['version'])+ ' and source code is for version '+str(release_version)+'!!')
                else:
                    log.info('No database upgrade needed.')
        self.upgrade_if_needed()
                
    def do_backup(self):
        None

    def upgrade_if_needed(self):
        if not release_version > self.cfg['version']:
            return False
        apply_upgrades=[i for i in range(self.cfg['version']+1,release_version+1)]
        print('Now will upgrade database versions: '+str(apply_upgrades))
        for version in apply_upgrades:
            for table in tables:
                eval('self.'+table+'('+str(version)+')')
                
        # ~ r.table('config').get(1).update({'version':release_version}).run()

        


    '''
    CONFIG TABLE UPGRADES
    '''
    def config(self,version):
        cfg=r.table('config').get(1).run()
        print('UPGRADING CONFIG TABLE TO VERSION '+str(version))
        if version == 1:
            try:
                ##### CONVERSION FIELDS
                cfg['grafana']={'active':cfg['engine']['carbon']['active'],
                                'url':cfg['engine']['carbon']['server'],
                                'web_port':80,
                                'carbon_port':cfg['engine']['carbon']['port'],
                                'graphite_port':3000}
                r.table('config').update(cfg).run()                
                ##### NEW FIELDS
                self.add_keys('config', [   {'resources':  {'code':False,
                                                            'url':'http://www.isardvdi.com:5050'}},
                                            {'voucher_access':{'active':False}},
                                            {'engine':{'api':{  "token": "fosdem", 
                                                                "url": 'http://isard-engine', 
                                                                "web_port": 5555}}}
                                        ])

                #### REMOVE FIELDS
                self.del_keys('config',[{'engine':{'carbon'}}])
                
            except Exception as e:
                log.error('Something went wrong while upgrading config!')
                log.error(e)
                exit(1)
                
        return True




    '''
    Upgrade general actions
    '''
    def add_keys(self,table,keys):
        for key in keys:
            r.table(table).update(key).run()
        
    def del_keys(self,table,keys):
        for key in keys:
            r.table(table).replace(r.row.without(key)).run()


