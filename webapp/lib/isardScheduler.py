# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
from decimal import Decimal
import random, queue
from threading import Thread
import time
from webapp import app
import rethinkdb as r

from .flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from ..lib.log import *

from apscheduler.schedulers.gevent import GeventScheduler
from apscheduler.jobstores.rethinkdb import RethinkDBJobStore

from datetime import datetime, timedelta

class isardScheduler():
    def __init__(self):
        '''
        JOB SCHEDULER
        '''
        self.rStore=RethinkDBJobStore()
        self.scheduler = GeventScheduler()
        self.scheduler.add_jobstore('rethinkdb',self.rStore, database='isard', table='scheduler_jobs')
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

    '''
    Scheduler actions
    '''
    def stop_domains():
        with app.app_context():
            r.table('domains').get_all('Started',index='status').update({'status':'Stopping'}).run(db.conn)
        
    def stop_domains_without_viewer():
        with app.app_context():
            r.table('domains').get_all('Started',index='status').filter({'viewer':{'client_since':False}}).update({'status':'Stopping'}).run(db.conn)
          
    def delete_old_stats():
        with app.app_context():
            r.table('domains_status').filter(r.row['when'] < int(time.time()) - 1200).delete().run(db.conn)  
            r.table('hypervisors_events').filter(r.row['when'] < int(time.time()) - 1200).delete().run(db.conn)  
            r.table('hypervisors_status').filter(r.row['when'] < int(time.time()) - 1200).delete().run(db.conn)  

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
   
