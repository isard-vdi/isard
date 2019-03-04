# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
from decimal import Decimal
import random, queue
from threading import Thread
import time, pytz
from webapp import app
import rethinkdb as r
#~ from flask import current_app

from .flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from ..lib.log import *

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.rethinkdb import RethinkDBJobStore

from datetime import datetime, timedelta

class isardScheduler():
    def __init__(self):
        '''
        JOB SCHEDULER
        '''
#<<<<<<< HEAD
#~ host=app.config['RETHINKDB_HOST'],
                                         #~ port=app.config['RETHINKDB_PORT'],
                                         #~ auth_key=app.config['RETHINKDB_AUTH']
        #~ rConn=r.connect(host=app.config['RETHINKDB_HOST'],
                         #~ port=app.config['RETHINKDB_PORT'],
                         #~ auth_key=app.config['RETHINKDB_AUTH'],
                         #~ db=app.config['RETHINKDB_DB'])
        self.rStore=RethinkDBJobStore()
#=======
        # ~ self.rStore=RethinkDBJobStore(host=app.config['RETHINKDB_HOST'],
                                         # ~ port=app.config['RETHINKDB_PORT'],
                                         # ~ auth_key=app.config['RETHINKDB_AUTH'])
#>>>>>>> fe171dc30ddd8a2dabafa7b2085cbb60e6432c35
        self.scheduler = BackgroundScheduler(timezone=pytz.timezone('UTC'))
        self.scheduler.add_jobstore('rethinkdb',self.rStore, database='isard', table='scheduler_jobs',host=app.config['RETHINKDB_HOST'],
                         port=app.config['RETHINKDB_PORT'],
                         auth_key=app.config['RETHINKDB_AUTH'])
        self.scheduler.remove_all_jobs()
        #~ scheduler.add_job(alarm, 'date', run_date=alarm_time, args=[datetime.now()])
        #~ app.sched.shutdown(wait=False)
        self.turnOn()
        
        
    def add_scheduler(self,kind,action,hour,minute):
        id=kind+'_'+action+'_'+str(hour)+str(minute)
        function=getattr(isardScheduler,action) 
        if kind == 'cron':
            self.scheduler.add_job(function, kind, hour=int(hour), minute=int(minute), jobstore=self.rStore, replace_existing=True, id=id)
        if kind == 'interval':
            self.scheduler.add_job(function, kind, hours=int(hour), minutes=int(minute), jobstore=self.rStore, replace_existing=True, id=id)
        if kind == 'date':
            alarm_time = datetime.now() + timedelta(hours=int(hour),minutes=int(minute))
            self.scheduler.add_job(function, kind, run_date=alarm_time, jobstore=self.rStore, replace_existing=True, id=id)
        with app.app_context():
            r.table('scheduler_jobs').get(id).update({'kind':kind,'action':action,'name':action.replace('_',' '),'hour':hour,'minute':minute}).run(db.conn)
        return True

    '''
    Scheduler actions
    '''
    def stop_domains():
        with app.app_context():
            r.table('domains').get_all('Started',index='status').update({'status':'Stopping'}).run(db.conn)
        
    def stop_domains_without_viewer():
        with app.app_context():
            r.table('domains').get_all('Started',index='status').filter({'viewer':{'client_since':False}}).update({'status':'Stopping'}).run(db.conn)

    def check_ephimeral_status():
        with app.app_context():
            domains=r.table('domains').get_all('Started',index='status').has_fields('ephimeral').pluck('id','ephimeral','history_domain').run(db.conn)
            t=time.time()
            for d in domains:
                if d['history_domain'][0]['when']+int(d['ephimeral']['minutes'])*60 < t:
                    r.table('domains').get(d['id']).update({'status':d['ephimeral']['action']}).run(db.conn)
                      
    def delete_old_stats(reduce_interval=300,delete_interval=86400): # 24h
        with app.app_context():
            # domains_status
            r.table('domains_status_history').filter(r.row['when'] < int(time.time()) - delete_interval).delete().run(db.conn)
            reduced=[]
            cursor = r.table('domains_status').filter(r.row['when'] < int(time.time()) - reduce_interval).order_by('when').run(db.conn)
            r.table('domains_status').filter(r.row['when'] < int(time.time()) - reduce_interval).delete().run(db.conn)
            i=0
            for c in cursor:
                if i % 50 == 0: reduced.append(c)
                i+=1
            r.table('domains_status_history').insert(reduced).run(db.conn)
            
            
            # Hypervisors_status
            r.table('hypervisors_status_history').filter(r.row['when'] < int(time.time()) - delete_interval).delete().run(db.conn)
            reduced=[]
            cursor = r.table('hypervisors_status').filter(r.row['when'] < int(time.time()) - reduce_interval).order_by('when').run(db.conn)
            r.table('hypervisors_status').filter(r.row['when'] < int(time.time()) - reduce_interval).delete().run(db.conn)
            i=0
            for c in cursor:
                if i % 50 == 0: reduced.append(c)
                i+=1
            r.table('hypervisors_status_history').insert(reduced).run(db.conn)
            
            # Hypervisors_events (does not grow at the same speed)
            r.table('hypervisors_events').filter(r.row['when'] < int(time.time()) - delete_interval).delete().run(db.conn)
      
    def turnOff(self):
        self.scheduler.shutdown()
    
    def turnOn(self):
        self.scheduler.start()
    
    def removeJobs(self):
        self.scheduler.remove_all_jobs()
    '''
    BULK ACTIONS
    '''
    def bulk_action(self,table,tbl_filter,tbl_update):
        with app.app_context():
            log.info('BULK ACTION: Table {}, Filter {}, Update {}'.format(table,filter, update))
            r.table(table).filter(filter).update(update).run(db.conn)
            #~ r.table(table).filter({'status':'Unknown'}).update({'status':'Stopping'}).run(db.conn)
   
