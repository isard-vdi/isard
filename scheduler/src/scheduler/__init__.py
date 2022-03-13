# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8

import logging as log
import os
import shutil

from flask import Flask, render_template, send_from_directory

print("Starting isard scheduler...")

app = Flask(__name__, static_url_path="")
app.url_map.strict_slashes = False

# Stores data for external apps poolling in ram
app.ram = {"secrets": {}}

from scheduler.lib.load_config import loadConfig

cfg = loadConfig(app)
if not cfg.init_app(app):
    exit(0)

"""
Scheduler
"""
from .lib.scheduler import Scheduler

log.info("Starting scheduler")
app.scheduler = Scheduler()

import os

debug = True if os.environ["LOG_LEVEL"] == "DEBUG" else False

"""'
Import all views
"""
# from .views import XmlView
from .views import SchedulerView
