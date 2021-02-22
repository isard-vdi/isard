# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8

from flask import Flask, send_from_directory, render_template

import os

app = Flask(__name__, static_url_path='')
app.url_map.strict_slashes = False

'''
App secret key for encrypting cookies
You can generate one with:
    import os
    os.urandom(24)
And paste it here.
'''
app.secret_key = "Change this key!//\xf7\x83\xbe\x17\xfa\xa3zT\n\\]m\xa6\x8bF\xdd\r\xf7\x9e\x1d\x1f\x14'"

print('Starting isard api...')

from api.libv2.load_config import loadConfig
cfg=loadConfig(app)
if not cfg.init_app(app): exit(0)

import logging as log

'''
Debug should be removed on production!
'''
if app.debug:
    log.warning('Debug mode: {}'.format(app.debug))
else:
    log.info('Debug mode: {}'.format(app.debug))

''''
Import all views
'''
from .views import UsersView
from .views import CommonView
from .views import DesktopsNonPersistentView
from .views import JumperViewerView
from .views import DesktopsPersistentView
from .views import XmlView
from .views import SundryView



