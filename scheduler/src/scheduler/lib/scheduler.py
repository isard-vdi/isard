#
#   Copyright © 2022 Josep Maria Viñolas Auquer
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from pathlib import Path
from uuid import uuid4

import pytz
from rethinkdb import RethinkDB

from scheduler import app

from .log import log

r = RethinkDB()

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from datetime import datetime, timedelta
from inspect import getmembers, isfunction

from apscheduler.jobstores.rethinkdb import RethinkDBJobStore
from apscheduler.schedulers.background import BackgroundScheduler

from .actions import Actions
from .exceptions import Error


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
            if job["kind"] == "date" and job["kwargs"].get("plan_id"):
                log.info(
                    "LOADING RESERVATION DATE JOB: -> Plan Id: {}, ITEM id: {}, Subitem id: {}".format(
                        job["kwargs"]["plan_id"],
                        job["kwargs"]["item_id"],
                        job["kwargs"]["subitem_id"],
                    )
                )
            else:
                log.info(
                    "LOADING JOBS: Job {} is a {} job".format(job["name"], job["kind"])
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
        actions = [action[0] for action in getmembers(Actions, isfunction)]
        return [
            {"id": f, "name": f.replace("_", " ")}
            for f in actions
            if not f.endswith("_kwargs") and f + "_kwargs" in actions
        ]

    def get_action_kwargs(self, action):
        try:
            function = getattr(Actions, action + "_kwargs")
        except:
            raise Error("bad_request", "Action not implemented")
        return function()

    def add_job(self, type, kind, action, hour, minute, id=None, kwargs=None):
        if type not in ["system", "bookings", "alerts"]:
            raise Error("bad_request", "Type not in system, bookings or alerts")
        if kind not in ["cron", "interval", "date"]:
            raise Error("bad_request", "Kind not in cron, interval or date")
        if int(hour) not in range(0, 23):
            raise Error("bad_request", "Hour range must be within 0-24")
        if int(minute) not in range(0, 59):
            raise Error("bad_request", "Minute range must be within 0-60")
        if not id:
            id = str(uuid4())
        if r.table("scheduler_jobs").get(id).run(db.conn):
            raise Error("conflict", "Same job id already exists")
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
                kwargs=kwargs,
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
                kwargs=kwargs,
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
                kwargs=kwargs,
            )
        with app.app_context():
            r.table("scheduler_jobs").get(id).update(
                {
                    "type": type,
                    "kind": kind,
                    "action": action,
                    "name": action.replace("_", " "),
                    "hour": hour,
                    "minute": minute,
                    "kwargs": kwargs,
                }
            ).run(db.conn)

    def add_advanced_interval_job(self, type, action, data, id=None, kwargs=None):
        try:
            function = getattr(Actions, action)
        except:
            raise Error("bad_request", "Action not implemented")
        if type not in ["system", "bookings", "alerts"]:
            raise Error("bad_request", "Type not in system, bookings or alerts")
        if not id:
            id = str(uuid4())

        self.scheduler.add_job(
            function,
            "interval",
            weeks=data["weeks"],
            days=data["days"],
            hours=data["hours"],
            minutes=data["minutes"],
            seconds=data["seconds"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            timezone=data["timezone"],
            jitter=data["jitter"],
            id=id,
            kwargs=kwargs,
        )
        with app.app_context():
            r.table("scheduler_jobs").get(id).update(
                {
                    "type": type,
                    "kind": "interval",
                    "action": action,
                    "name": action.replace("_", " "),
                    "hour": "interval",
                    "minute": "interval",
                    "kwargs": kwargs,
                }
            ).run(db.conn)

    def add_advanced_date_job(self, type, action, date, id=None, kwargs=None):
        try:
            function = getattr(Actions, action)
        except:
            raise Error("bad_request", "Action not implemented")

        if not id:
            id = str(uuid4())
        date = datetime.strptime(date, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
        self.scheduler.add_job(
            function,
            "date",
            run_date=date,
            jobstore=self.rStore,
            replace_existing=True,
            id=id,
            kwargs=kwargs,
        )
        with app.app_context():
            r.table("scheduler_jobs").get(id).update(
                {
                    "type": type,
                    "kind": "date",
                    "action": action,
                    "name": action.replace("_", " "),
                    "date": date,
                    "kwargs": kwargs,
                }
            ).run(db.conn)

    def remove_job(self, job_id):
        try:
            self.scheduler.remove_job(job_id)
        except:
            raise Error(
                "not_found",
                "Job id " + str(job_id) + " not found. Probably was already deleted",
            )

    def remove_job_startswith(self, job_id):
        jobs = (
            r.table("scheduler_jobs")
            .filter(lambda job: job["id"].match("^" + job_id))
            .run(db.conn)
        )
        for job in jobs:
            try:
                self.remove_job(job["id"])
            except:
                log.info(
                    "Job id "
                    + str(job["id"])
                    + " not found. Probably was already deleted"
                )

    def turnOff(self):
        self.scheduler.shutdown()

    def turnOn(self):
        self.scheduler.start()

    def removeJobs(self):
        self.scheduler.remove_all_jobs()
