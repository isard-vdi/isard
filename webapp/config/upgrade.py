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



tables=['config','hypervisors']

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
                
        r.table('config').get(1).update({'version':release_version}).run()

        


    '''
    CONFIG TABLE UPGRADES
    '''
    def config(self,version):
        cfg=r.table('config').get(1).run()
        print('UPGRADING CONFIG TABLE TO VERSION '+str(version))
        if version == 1:
            ##### PRE CHECKS    
            if self.check_done( cfg,
                                ['grafana','resources','voucher_access',['engine','api','token']],
                                [['engine','carbon']]): return
            
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
    CONFIG TABLE UPGRADES
    '''
    def hypervisors(self,version):
        hyps=list(r.table('hypervisors').run())
        print('UPGRADING HYPERVISORS VERSION '+str(version))
        if version == 1:
            for hyp in hyps:
                ##### PRE CHECKS    
                if self.check_done( hyp,
                                    ['viewer_hostname','viewer_nat_hostname'],
                                    []): continue                
                try:
                    ##### CONVERSION FIELDS
                    # ~ hyp['field']={'active':cfg['engine']['carbon']['active'],
                                    # ~ 'url':cfg['engine']['carbon']['server'],
                                    # ~ 'web_port':80,
                                    # ~ 'carbon_port':cfg['engine']['carbon']['port'],
                                    # ~ 'graphite_port':3000}
                    # ~ r.table('config').update(cfg).run()  
                                  
                    ##### NEW FIELDS
                    self.add_keys('hypervisors', [  {'viewer_hostname': hyp['hostname']},
                                                    {'viewer_nat_hostname': hyp['hostname']}
                                            ])

                    #### REMOVE FIELDS
                    # ~ self.del_keys('config',[{'engine':{'carbon'}}])
                    
                except Exception as e:
                    log.error('Something went wrong while upgrading hypervisors!')
                    log.error(e)
                    exit(1)
                
        return True

    '''
    Upgrade general actions
    '''
    def add_keys(self,table,keys,id=False):
        for key in keys:
            if id is False:
                r.table(table).update(key).run()
            else:
                r.table(table).get(id).update(key).run()
        
    def del_keys(self,table,keys,id=False):
        for key in keys:
            if id is False:
                r.table(table).replace(r.row.without(key)).run()
            else:
                r.table(table).get(id).replace(r.row.without(key)).run()

    def check_done(self,dict,must=[],mustnot=[]):
        done=False
        # ~ check_done(cfg,['grafana','resources','voucher_access',{'engine':{'api':{'token'}}}],[{'engine':{'carbon'}}])
        for m in must:
            if type(m) is str: m=[m]
            if self.keys_exists(dict,m):
                done=True
                # ~ print(str(m)+' exists on dict. ok')
            # ~ else:
                # ~ print(str(m)+' not exists on dict. KO')

        for mn in mustnot:
            if type(mn) is str: mn=[mn]
            if not self.keys_exists(dict,mn):
                done=True
                # ~ print(str(mn)+' not exists on dict. ok')                
            # ~ else:
                # ~ print(str(mn)+' exists on dict. KO')
        return done
                
                
    def keys_exists(self, element, keys):
        '''
        Check if *keys (nested) exists in `element` (dict).
        '''
        if type(element) is not dict:
            raise AttributeError('keys_exists() expects dict as first argument.')
        if len(keys) == 0:
            raise AttributeError('keys_exists() expects at least two arguments, one given.')

        _element = element
        for key in keys:
            try:
                _element = _element[key]
            except KeyError:
                return False
        return True
