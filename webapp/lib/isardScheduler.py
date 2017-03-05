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
        #~ app.scheduler.remove_all_jobs()
        #~ scheduler.add_job(alarm, 'date', run_date=alarm_time, args=[datetime.now()])
        #~ app.sched.shutdown(wait=False)
        self.turnOn()
        
        
    def addCron(self,table,filter,update,hour,minute):
        alarm_time = datetime.now() + timedelta(seconds=10)
        self.scheduler.add_job(self.bulk_action,'cron', hour=hour, minute=minute, args=[table,filter,update], jobstore=self.rStore, replace_existing=True, id='p2')

    def addDate(self,table,filter,update,seconds):
        alarm_time = datetime.now() + timedelta(seconds=seconds)
        self.scheduler.add_job(self.bulk_action,'date', run_date=alarm_time, args=[table,filter,update], jobstore=self.rStore, replace_existing=True, id='p1')

    def addInterval(self,table,filter,update,seconds):
        alarm_time = datetime.now() + timedelta(seconds=10)
        self.scheduler.add_job(self.bulk_action,'interval', run_date=alarm_time, args=[table,filter,update], jobstore=self.rStore, replace_existing=True, id='p1')


    #~ def getJobs(self):
        #~ return self.scheduler.print_jobs()
        
    def turnOff(self):
        self.scheduler.shutdown()
    
    def turnOn(self):
        self.scheduler.start()
    
    def removeJobs(self):
        self.scheduler.remove_all_jobs()
    '''
    BULK ACTIONS
    '''
    def bulk_action(self,table,filter,update):
        with app.app_context():
            log.info('BULK ACTION: Table {}, Filter {}, Update {}'.format(table,filter, update))
            r.table(table).filter(filter).update(update).run(db.conn)
            #~ r.table(table).filter({'status':'Unknown'}).update({'status':'Stopping'}).run(db.conn)
   
