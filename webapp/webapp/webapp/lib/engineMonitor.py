from flask import Flask, render_template, session, request
from flask_login import login_required, login_user, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, rooms, disconnect, send

from flask import render_template, Response, request, redirect, url_for, stream_with_context, flash
from webapp import app
from flask_login import login_required, login_user, logout_user, current_user
import time
import json
import threading
import sys
import requests

from ..lib.log import *

import rethinkdb as r
from rethinkdb.errors import ReqlDriverError
from ..lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

#~ from .decorators import ownsid
from webapp import app
app.enginestatus={'code':1,'status':'unknown','desc':'no engine api answering','data':False}

#socketio = SocketIO(app)

from .telegram import tsend
engineth=None

## Engine Monitor
class EngineMonitorThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False
        tsend('Engine monitoring started.')

    def run(self):
        #errors=12
        errors=True
        last=True
        while errors:
            time.sleep(30)
            try:
                s=requests.get('http://isard-engine:5555/engine_info')
                if s.status_code != 200: 
                    data={'code':1,'status':'unknown','desc':'ERROR: Engine api status code '+str(s.status_code),'data':False}
                    if last == True:
                        last = False
                        # Send ko message
                        tsend(data['desc'])
                    #errors=errors-1
                    continue
                dict=s.json()
                status={'background': dict['background_is_alive'],
                        'broom':dict['broom_thread_is_alive'],
                        'changes_domains':dict['changes_domains_thread_is_alive'],
                        'changes_hypers':dict['changes_hyps_thread_is_alive'],
                        'changes_downloads':dict['download_changes_thread_is_alive'],
                        'events':dict['event_thread_is_alive'],
                        'disk_operations':len(dict['disk_operations_threads'])>0,
                        'long_operations':len(dict['long_operations_threads'])>0,
                        'working':len(dict['working_threads'])>0}
                if all(value for value in status.values()) == True:
                    data={'code':0,'status':'ok','desc':'OK: Engine recovered','data':status}
                    if last == False:
                        last = True
                        # Send recovery message
                        tsend(data['desc'])
                        #tsend(json.dumps(status))
                else:
                    data={'code':2,'status':'fail','desc':'ERROR: Engine threads with errors.','data':status}
                    if last == True:
                        last = False
                        # Send ko partial error message
                        tsend(data['desc'])
                        #tsend(json.dumps(status))                        
                #errors=12

            except Exception as e:
                data={'code':1,'status':'unknown','desc':'ERROR: Engine api not answering.','data':False}
                if last == True:
                    last = False
                    # Send ko message
                    tsend(data['desc'])
                    #tsend(json.dumps(data['status']))
                #errors=errors-1                
                print('EngineMonitor internal error: '+str(e))
                log.error('EngineMonitor internal error: '+str(e))
        print('EngineMonitor ENDED. Too many retries!!!!!!!')
        log.error('EngineMonitor ENDED. Too many retries!!!!!!!')      

def start_thread():
    global engineth
    if not (app.config['TELEGRAM_BOT_TOKEN'] and app.config['TELEGRAM_BOT_CHAT_ID']):
        print('No telegram monitor bot configured. Not starting engine monitoring.')
    else:
        if engineth == None:
            engineth = EngineMonitorThread()
            engineth.daemon = True
            engineth.start()
            log.info('EngineMonitor Started')

            