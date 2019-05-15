# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import rethinkdb as r
import time, sys, requests

from ..lib.log import *
from ..auth.authentication import Password
from ..lib.load_config import load_config


''' 
Update to new database release version when new code version release
'''
release_version = 7
tables=['config','hypervisors','hypervisors_pools','domains','media','graphics']


class Upgrade(object):
    def __init__(self):
        
        # ~ self.rele = 9
        
        self.conf=load_config()
        
        self.conn=False
        self.cfg=False
        try:
            self.conn = r.connect( self.conf['RETHINKDB_HOST'],self.conf['RETHINKDB_PORT'],self.conf['RETHINKDB_DB']).repl()
        except Exception as e:
            log.error(e)
            self.conn=False

        if self.conn is not False and r.db_list().contains(self.conf['RETHINKDB_DB']).run():
            if r.table_list().contains('config').run():
                ready=False
                while not ready:
                    try:
                        self.cfg = r.table('config').get(1).run()
                        ready = True
                    except Exception as e:
                        log.info('Waiting for database to be ready...')
                        time.sleep(1)
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
        log.info('Now will upgrade database versions: '+str(apply_upgrades))
        for version in apply_upgrades:
            for table in tables:
                eval('self.'+table+'('+str(version)+')')
                
        r.table('config').get(1).update({'version':release_version}).run()

        


    '''
    CONFIG TABLE UPGRADES
    '''
    def config(self,version):
        table='config'
        d=r.table(table).get(1).run()     
        log.info('UPGRADING '+table+' TABLE TO VERSION '+str(version))
        if version == 1:
            
            ''' CONVERSION FIELDS PRE CHECKS '''
            try:
                if not self.check_done( d,
                                    ['grafana'],
                                    [['engine','carbon']]):  
                    ##### CONVERSION FIELDS
                    cfg['grafana']={'active':d['engine']['carbon']['active'],
                                    'url':d['engine']['carbon']['server'],
                                    'web_port':80,
                                    'carbon_port':d['engine']['carbon']['port'],
                                    'graphite_port':3000}
                    r.table(table).update(cfg).run()
            except Exception as e:
                log.error('Could not update table '+table+' conversion fields for db version '+version+'!')
                log.error('Error detail: '+str(e))
                
            ''' NEW FIELDS PRE CHECKS '''   
            try:
                if not self.check_done( d,
                                    ['resources','voucher_access',['engine','api','token']],
                                    []):                                      
                    ##### NEW FIELDS
                    self.add_keys(table, [   
                                            {'resources':  {    'code':False,
                                                                'url':'http://www.isardvdi.com:5050'}},
                                            {'voucher_access':{'active':False}},
                                            {'engine':{'api':{  "token": "fosdem", 
                                                                "url": 'http://isard-engine', 
                                                                "web_port": 5555}}}])
            except Exception as e:
                log.error('Could not update table '+table+' new fields for db version '+version+'!')
                log.error('Error detail: '+str(e))
                
            ''' REMOVE FIELDS PRE CHECKS '''   
            try:
                if not self.check_done( d,
                                    [],
                                    [['engine','carbon']]):   
                    #### REMOVE FIELDS
                    self.del_keys(table,[{'engine':{'carbon'}}])
            except Exception as e:
                log.error('Could not update table '+table+' remove fields for db version '+version+'!')
                log.error('Error detail: '+str(e))

        if version == 5:
            d['engine']['log']['log_level'] = 'WARNING'
            r.table(table).update(d).run()                

        if version == 6:
            
            ''' CONVERSION FIELDS PRE CHECKS '''
            try:
                url=d['engine']['grafana']['url']
            except:
                url=""
            try:
                if not self.check_done( d,
                                    [],
                                    ['engine']):  
                    ##### CONVERSION FIELDS
                    d['engine']['grafana']={"active": False ,
                                            "carbon_port": 2004 ,
                                            "interval": 5,
                                            "hostname": "isard-grafana",
                                            "url": url}
                    r.table(table).update(d).run()
            except Exception as e:
                log.error('Could not update table '+table+' conversion fields for db version '+version+'!')
                log.error('Error detail: '+str(e))
                
            # ~ ''' NEW FIELDS PRE CHECKS '''   
            # ~ try:
                # ~ if not self.check_done( d,
                                    # ~ ['resources','voucher_access',['engine','api','token']],
                                    # ~ []):                                      
                    # ~ ##### NEW FIELDS
                    # ~ self.add_keys(table, [   
                                            # ~ {'resources':  {    'code':False,
                                                                # ~ 'url':'http://www.isardvdi.com:5050'}},
                                            # ~ {'voucher_access':{'active':False}},
                                            # ~ {'engine':{'api':{  "token": "fosdem", 
                                                                # ~ "url": 'http://isard-engine', 
                                                                # ~ "web_port": 5555}}}])
            # ~ except Exception as e:
                # ~ log.error('Could not update table '+table+' new fields for db version '+version+'!')
                # ~ log.error('Error detail: '+str(e))
                
            ''' REMOVE FIELDS PRE CHECKS '''   
            try:
                if not self.check_done( d,
                                    [],
                                    ['grafana']):   
                    #### REMOVE FIELDS
                    self.del_keys(table,['grafana'])
            except Exception as e:
                log.error('Could not update table '+table+' remove fields for db version '+version+'!')
                log.error('Error detail: '+str(e))
        return True
        
    '''
    HYPERVISORS TABLE UPGRADES
    '''
    def hypervisors(self,version):
        table='hypervisors'
        data=list(r.table(table).run())
        log.info('UPGRADING '+table+' VERSION '+str(version))
        if version == 1:
            for d in data:
                id=d['id']
                d.pop('id',None)                
                
                ''' CONVERSION FIELDS PRE CHECKS ''' 
                # ~ try:  
                    # ~ if not self.check_done( d,
                                        # ~ [],
                                        # ~ []):  
                        ##### CONVERSION FIELDS
                        # ~ cfg['field']={}
                        # ~ r.table(table).update(cfg).run()  
                # ~ except Exception as e:
                    # ~ log.error('Could not update table '+table+' remove fields for db version '+version+'!')
                    # ~ log.error('Error detail: '+str(e))
   
                ''' NEW FIELDS PRE CHECKS '''   
                try: 
                    if not self.check_done( d,
                                        ['viewer_hostname','viewer_nat_hostname'],
                                        []):                                     
                        ##### NEW FIELDS
                        self.add_keys(  table, 
                                        [   {'viewer_hostname': d['hostname']},
                                            {'viewer_nat_hostname': d['hostname']} ],
                                            id=id)
                except Exception as e:
                    log.error('Could not update table '+table+' remove fields for db version '+version+'!')
                    log.error('Error detail: '+str(e))
                
                ''' REMOVE FIELDS PRE CHECKS ''' 
                # ~ try:  
                    # ~ if not self.check_done( d,
                                        # ~ [],
                                        # ~ []):   
                        #### REMOVE FIELDS
                        # ~ self.del_keys(TABLE,[])
                # ~ except Exception as e:
                    # ~ log.error('Could not update table '+table+' remove fields for db version '+version+'!')
                    # ~ log.error('Error detail: '+str(e))                    

        if version == 2:
            for d in data:
                id=d['id']
                d.pop('id',None)                
                
                ''' CONVERSION FIELDS PRE CHECKS ''' 
                # ~ try:  
                    # ~ if not self.check_done( d,
                                        # ~ [],
                                        # ~ []):  
                        ##### CONVERSION FIELDS
                        # ~ cfg['field']={}
                        # ~ r.table(table).update(cfg).run()  
                # ~ except Exception as e:
                    # ~ log.error('Could not update table '+table+' remove fields for db version '+version+'!')
                    # ~ log.error('Error detail: '+str(e))
   
                ''' NEW FIELDS PRE CHECKS '''   
                try: 
                    if not self.check_done( d,
                                        ['viewer_nat_offset'],
                                        []):                                     
                        ##### NEW FIELDS
                        self.add_keys(  table, 
                                        [   {'viewer_nat_offset':0} ],
                                            id=id)
                except Exception as e:
                    log.error('Could not update table '+table+' add fields for db version '+version+'!')
                    log.error('Error detail: '+str(e))
                
                ''' REMOVE FIELDS PRE CHECKS ''' 
                # ~ try:  
                    # ~ if not self.check_done( d,
                                        # ~ [],
                                        # ~ []):   
                        #### REMOVE FIELDS
                        # ~ self.del_keys(TABLE,[])
                # ~ except Exception as e:
                    # ~ log.error('Could not update table '+table+' remove fields for db version '+version+'!')
                    # ~ log.error('Error detail: '+str(e))                    
                                                    
        return True

    '''
    HYPERVISORS_POOLS TABLE UPGRADES
    '''
    def hypervisors_pools(self,version):
        table='hypervisors_pools'
        data=list(r.table(table).run())
        log.info('UPGRADING '+table+' VERSION '+str(version))
        if version == 1 or version == 3:
            for d in data:
                id=d['id']
                d.pop('id',None)
                try:
                    ''' CONVERSION FIELDS PRE CHECKS '''   
                    # ~ if not self.check_done( d,
                                        # ~ [],
                                        # ~ []):  
                        ##### CONVERSION FIELDS
                        # ~ cfg['field']={}
                        # ~ r.table(table).update(cfg).run()   

                    ''' NEW FIELDS PRE CHECKS '''   
                    if not self.check_done( d,
                                        [['paths','media']],
                                        []):                                   
                        ##### NEW FIELDS
                        media=d['paths']['groups'] #.copy()
                        # ~ print(media)
                        medialist=[]
                        for m in media:
                            m['path']=m['path'].split('groups')[0]+'media'
                            medialist.append(m)
                        d['paths']['media']=medialist
                        self.add_keys(table, [{'paths':d['paths']}],
                                             id=id)

                    ''' REMOVE FIELDS PRE CHECKS '''   
                    if not self.check_done( d,
                                        [],
                                        [['paths','isos']]):   
                        #### REMOVE FIELDS
                        self.del_keys(table,[{'paths':{'isos'}}])
                    
                except Exception as e:
                    log.error('Something went wrong while upgrading hypervisors!')
                    log.error(e)
                    exit(1)

        if version == 4:
            for d in data:
                id = d['id']
                d.pop('id', None)
                try:
                    ''' CONVERSION FIELDS PRE CHECKS '''
                    # ~ if not self.check_done( d,
                    # ~ [],
                    # ~ []):
                    ##### CONVERSION FIELDS
                    # ~ cfg['field']={}
                    # ~ r.table(table).update(cfg).run()

                    ''' NEW FIELDS PRE CHECKS '''
                    if not self.check_done(d,
                                           [['cpu_host_model']],
                                           []):
                        ##### NEW FIELDS
                        self.add_keys(table, [{'cpu_host_model': 'host-model'}],
                                      id=id)

                    # ''' REMOVE FIELDS PRE CHECKS '''
                    # if not self.check_done(d,
                    #                        [],
                    #                        [['paths', 'isos']]):
                    #     #### REMOVE FIELDS
                    #     self.del_keys(table, [{'paths': {'isos'}}])

                except Exception as e:
                    log.error('Something went wrong while upgrading hypervisors!')
                    log.error(e)
                    exit(1)
                
        return True

    '''
    DOMAINS TABLE UPGRADES
    '''
    def domains(self,version):
        table='domains'
        data=list(r.table(table).run())
        log.info('UPGRADING '+table+' VERSION '+str(version))
        if version == 2:
            for d in data:
                id=d['id']
                d.pop('id',None)                
                
                ''' CONVERSION FIELDS PRE CHECKS ''' 
                # ~ try:  
                    # ~ if not self.check_done( d,
                                        # ~ [],
                                        # ~ []):  
                        ##### CONVERSION FIELDS
                        # ~ cfg['field']={}
                        # ~ r.table(table).update(cfg).run()  
                # ~ except Exception as e:
                    # ~ log.error('Could not update table '+table+' remove fields for db version '+version+'!')
                    # ~ log.error('Error detail: '+str(e))
   
                ''' NEW FIELDS PRE CHECKS '''   
                try: 
                    if not self.check_done( d,
                                        ['preferences'],
                                        []):                                     
                        ##### NEW FIELDS
                        self.add_keys(  table, 
                                        [   {'options': {'viewers':{'spice':{'fullscreen':False}}}}],
                                            id=id)
                except Exception as e:
                    log.error('Could not update table '+table+' add fields for db version '+version+'!')
                    log.error('Error detail: '+str(e))
                
                ''' REMOVE FIELDS PRE CHECKS ''' 
                # ~ try:  
                    # ~ if not self.check_done( d,
                                        # ~ [],
                                        # ~ []):   
                        #### REMOVE FIELDS
                        # ~ self.del_keys(TABLE,[])
                # ~ except Exception as e:
                    # ~ log.error('Could not update table '+table+' remove fields for db version '+version+'!')
                    # ~ log.error('Error detail: '+str(e))                    
        if version == 7:
            for d in data:
                id = d['id']
                d.pop('id', None)

                ''' CONVERSION FIELDS PRE CHECKS '''
                # ~ try:
                # ~ if not self.check_done( d,
                # ~ [],
                # ~ []):
                ##### CONVERSION FIELDS
                # ~ cfg['field']={}
                # ~ r.table(table).update(cfg).run()
                # ~ except Exception as e:
                # ~ log.error('Could not update table '+table+' remove fields for db version '+version+'!')
                # ~ log.error('Error detail: '+str(e))

                ''' NEW FIELDS PRE CHECKS '''
                try:
                    if not self.check_done(d,
                                           ['preferences'],
                                           []):
                        ##### NEW FIELDS
                        self.add_keys(table,
                                      [{'options': {'viewers': {'id_graphics': 'default'}}}],
                                      id=id)
                except Exception as e:
                    log.error('Could not update table ' + table + ' add fields for db version ' + version + '!')
                    log.error('Error detail: ' + str(e))

        return True

    '''
    DOMAINS TABLE UPGRADES
    '''
    def media(self,version):
        table='media'
        log.info('UPGRADING '+table+' VERSION '+str(version))
        #~ data=list(r.table(table).run())
        if version == 3:
            ''' KEY INDEX FIELDS PRE CHECKS ''' 
            self.index_create(table,['kind']) 
            
            #~ for d in data:
                #~ id=d['id']
                #~ d.pop('id',None)                
                #~ ''' CONVERSION FIELDS PRE CHECKS ''' 
                # ~ try:  
                    # ~ if not self.check_done( d,
                                        # ~ [],
                                        # ~ []):  
                        ##### CONVERSION FIELDS
                        # ~ cfg['field']={}
                        # ~ r.table(table).update(cfg).run()  
                # ~ except Exception as e:
                    # ~ log.error('Could not update table '+table+' remove fields for db version '+version+'!')
                    # ~ log.error('Error detail: '+str(e))
   
                #~ ''' NEW FIELDS PRE CHECKS '''   
                #~ try: 
                    #~ if not self.check_done( d,
                                        #~ ['preferences'],
                                        #~ []):                                     
                        #~ ##### NEW FIELDS
                        #~ self.add_keys(  table, 
                                        #~ [   {'options': {'viewers':{'spice':{'fullscreen':False}}}}],
                                            #~ id=id)
                #~ except Exception as e:
                    #~ log.error('Could not update table '+table+' add fields for db version '+version+'!')
                    #~ log.error('Error detail: '+str(e))
                
                #~ ''' REMOVE FIELDS PRE CHECKS ''' 
                # ~ try:  
                    # ~ if not self.check_done( d,
                                        # ~ [],
                                        # ~ []):   
                        #### REMOVE FIELDS
                        # ~ self.del_keys(TABLE,[])
                # ~ except Exception as e:
                    # ~ log.error('Could not update table '+table+' remove fields for db version '+version+'!')
                    # ~ log.error('Error detail: '+str(e))                    
         
        return True

    '''
    DOMAINS TABLE GRAPHICS
    '''
    def graphics(self,version):
        table='graphics'
        log.info('UPGRADING '+table+' VERSION '+str(version))
        #~ data=list(r.table(table).run())
        if version == 7:
            r.table(table).delete().run()
            r.table('graphics').insert([
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
                     'vlc': {
                         'options': {}}
                 },
                 }
            ]).run()

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


    def index_create(self,table,indexes):
        with app.app_context():
            indexes_ontable=r.table(table).index_list().run()
            apply_indexes = [mi for mi in indexes if mi not in indexes_ontable]
            for i in apply_indexes:
                r.table(table).index_create(i).run()
                r.table(table).index_wait(i).run()
