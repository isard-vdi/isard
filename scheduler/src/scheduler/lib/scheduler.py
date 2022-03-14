# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import time

import pytz
from flask import current_app
from rethinkdb import RethinkDB

from scheduler import app

from .log import log

r = RethinkDB()

import traceback

from rethinkdb.errors import ReqlTimeoutError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from datetime import datetime, timedelta
from inspect import getmembers, isfunction

from apscheduler.jobstores.rethinkdb import RethinkDBJobStore
from apscheduler.schedulers.background import BackgroundScheduler

from .actions import Actions
from .exceptions import Error

# class apscheduler.jobstores.rethinkdb.RethinkDBJobStore(database='apscheduler',
# table='jobs', client=None, pickle_protocol=pickle.HIGHEST_PROTOCOL, **connect_args)


class Scheduler:
    def __init__(self):
        """
        JOB SCHEDULER
        """
        self.rStore = RethinkDBJobStore()

        self.scheduler = BackgroundScheduler(timezone=pytz.timezone("UTC"))
        log.info("Attaching to rethinkdb job store")
        self.scheduler.add_jobstore(
            "rethinkdb",
            self.rStore,
            database="isard",
            table="scheduler_jobs",
            host=app.config["RETHINKDB_HOST"],
            port=app.config["RETHINKDB_PORT"],
            auth_key="",
        )
        # self.scheduler.remove_all_jobs()
        # self.scheduler.add_job(alarm, 'date', run_date=alarm_time, args=[datetime.now()])
        # app.sched.shutdown(wait=False)
        # self.add_scheduler('interval','stop_shutting_down_desktops','0','1')

        for job in self.load_jobs():
            log.info(
                "LOADING JOBS: Job {} is a {} programmed at hour {} and minute {}".format(
                    job["name"], job["kind"], job["hour"], job["minute"]
                )
            )
        self.turnOn()
        # log.info('Adding default shutting_down_desktops job')
        # self.add_scheduler("interval", "stop_shutting_down_desktops", "0", "1")

    def load_jobs(self, job_id=None):
        with app.app_context():
            if job_id:
                job = (
                    r.table("scheduler_jobs")
                    .get(job_id)
                    .without("job_state")
                    .default(None)
                    .run(db.conn)
                )
                if not job:
                    raise Error("not_found")
                return job
            else:
                return list(r.table("scheduler_jobs").without("job_state").run(db.conn))

    def list_actions(self):
        return [f[0] for f in getmembers(Actions, isfunction)]

    def add_job(self, kind, action, hour, minute):
        if kind not in ["cron", "interval", "date"]:
            raise Error("bad_request", "Kind not in cron, interval or date")
        if int(hour) not in range(0, 23):
            raise Error("bad_request", "Hour range must be within 0-24")
        if int(minute) not in range(0, 59):
            raise Error("bad_request", "Minute range must be within 0-60")
        id = kind + "_" + action + "_" + str(hour) + "_" + str(minute)
        if r.table("scheduler_jobs").get(id).run(db.conn):
            raise Error("conflict", "Same job already exists")
        try:
            function = getattr(Actions, action)
        except:
            raise Error("bad_request", "Action not implemented")
        if kind == "cron":
            self.scheduler.add_job(
                function,
                kind,
                hour=int(hour),
                minute=int(minute),
                jobstore=self.rStore,
                replace_existing=True,
                id=id,
            )
        if kind == "interval":
            self.scheduler.add_job(
                function,
                kind,
                hours=int(hour),
                minutes=int(minute),
                jobstore=self.rStore,
                replace_existing=True,
                id=id,
            )
        if kind == "date":
            alarm_time = datetime.now() + timedelta(
                hours=int(hour), minutes=int(minute)
            )
            self.scheduler.add_job(
                function,
                kind,
                run_date=alarm_time,
                jobstore=self.rStore,
                replace_existing=True,
                id=id,
            )
        with app.app_context():
            r.table("scheduler_jobs").get(id).update(
                {
                    "kind": kind,
                    "action": action,
                    "name": action.replace("_", " "),
                    "hour": hour,
                    "minute": minute,
                }
            ).run(db.conn)

    def remove_job(self, job_id):
        try:
            self.scheduler.remove_job(job_id)
        except:
            raise Error("not_found", "Job id not found")

    def turnOff(self):
        self.scheduler.shutdown()

    def turnOn(self):
        self.scheduler.start()

    def removeJobs(self):
        self.scheduler.remove_all_jobs()
