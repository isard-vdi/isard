# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8

from flask import Flask, send_from_directory
from .lib.log import *
import os

app = Flask(__name__, static_url_path='')

'''
App secret key for encrypting cookies
You can generate one with:
    import os
    os.urandom(24)
And paste it here.
'''
app.secret_key = "Change this key!//\xf7\x83\xbe\x17\xfa\xa3zT\n\\]m\xa6\x8bF\xdd\r\xf7\x9e\x1d\x1f\x14'"


from webapp.lib.load_config import loadConfig
cfg=loadConfig(app)
if not cfg.init_app(app): exit(0)

'''
Debug should be removed on production!
'''
app.debug = True
if app.debug:
    log.warning('Debug mode: {}'.format(app.debug))
else:
    log.info('Debug mode: {}'.format(app.debug))

'''
Populate database if not exists
'''
from .config.populate import Populate
p=Populate()
if not p.database(): exit(0)
p.defaults()


'''
Scheduler
'''
from .lib.isardScheduler import isardScheduler
app.scheduler=isardScheduler()

'''
Authentication types
'''
from .auth import authentication
app.localuser=authentication.LocalUsers()


'''
Serve static files
'''
@app.route('/build/<path:path>')
def send_build(path):
    return send_from_directory(os.path.join(app.root_path, 'bower_components/gentelella/build'), path)
    
@app.route('/vendors/<path:path>')
def send_vendors(path):
    return send_from_directory(os.path.join(app.root_path, 'bower_components/gentelella/vendors'), path)

@app.route('/templates/<path:path>')
def send_templates(path):
    return send_from_directory(os.path.join(app.root_path, 'templates'), path)

@app.route('/bower_components/<path:path>')
def send_bower(path):
    return send_from_directory(os.path.join(app.root_path, 'bower_components'), path)

#~ @app.route('/socket.io')
#~ def send_socketio(path):
    #~ return send_from_directory(os.path.join(app.root_path, 'bower_components/socket.io-client/lib/socket.js'), path)
    
@app.route('/isard_dist/<path:path>')
def send_isardist(path):
    return send_from_directory(os.path.join(app.root_path, 'isard_dist'), path)

@app.route('/static/<path:path>')
def send_static_js(path):
    return send_from_directory(os.path.join(app.root_path, 'static'), path)
    
'''
Import all views
'''
from .views import LoginViews
from .views import DesktopViews
from .views import TemplateViews
from .views import IsosViews
from .views import ClassroomViews
from .views import ProfileViews
from .views import AboutViews

from .admin.views import AdminViews
from .admin.views import AdminUsersViews
from .admin.views import AdminDomainsViews
#~ from .admin.views import AdminIsosViews
from .admin.views import AdminHypersViews
from .admin.views import ClassroomViews
from .admin.views import AdminGraphsViews



