from gevent import monkey
monkey.patch_all()

import time
import json
#~ from threading import Thread
import threading
from flask import Flask, render_template, session, request
from flask_login import login_required, login_user, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, rooms, disconnect, send

from webapp.lib import api
from webapp import app

import rethinkdb as r
from webapp.lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

#~ app = Flask(__name__)
#~ app.debug = True
#~ app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)
thread = None

app.isardapi = api.isard()

#~ def background_stuff():
    #~ """ Let's do it a bit cleaner """
    #~ with app.app_context():
        #~ for c in r.table('domains').changes(include_initial=False).run(db.conn):
            #~ time.sleep(1)
            #~ t = str(time.clock())
            #~ socketio.emit('message', {'data': 'This is data', 'time': t}, namespace='/user')


## Domains Threading

class DomainsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        with app.app_context():
            namespace='/domains'
            for c in r.table('domains').changes(include_initial=False).run(db.conn):
                if self.stop==True: break
                try:
                    if c['new_val'] is None:
                        data=c['old_val']
                        event='desktop_delete' if data['kind']=='desktop' else 'template_delete'
                    #~ elif c['old_val'] is None:
                        #~ data=c['new_val']
                        #~ event='desktop_add' if data['kind']=='desktop' else 'template_add'
                    else:
                        # Status
                        data=c['new_val']
                        event='desktop_data' if data['kind']=='desktop' else 'template_data'
                    socketio.emit(event, 
                                    json.dumps(app.isardapi.f.flatten_dict(data)), 
                                    namespace=namespace, 
                                    room='user_'+data['user'])
                    socketio.emit('user_quota', 
                                    json.dumps(app.isardapi.get_user_quotas(data['user'])), 
                                    namespace=namespace, 
                                    room='user_'+data['user'])
                    ## Admins should receive all updates on /admin namespace
                    socketio.emit(event, 
                                    json.dumps(app.isardapi.f.flatten_dict(data)), 
                                    namespace='/admin_domains', 
                                    room='admins')
                except Exception as e:
                    log.error('DomainsThread error:'+e)

def start_domains_thread():
    global thread
    if thread is None:
        thread = DomainsThread()
        thread.daemon = True
        thread.start()
        print('UsersThread Started')


## Domains namespace
@socketio.on('connect', namespace='/domains')
def socketio_domains_connect():
    #~ print('sid:'+request.sid)
    join_room('user_'+current_user.username)
    socketio.emit('user_quota', 
                    json.dumps(app.isardapi.get_user_quotas(current_user.username, current_user.quota)), 
                    namespace='/domains', 
                    room='user_'+current_user.username)
    
@socketio.on('disconnect', namespace='/domains')
def socketio_domains_disconnect():
    print('user:'+current_user.username+' disconnected')

@socketio.on('domain_update', namespace='/domains')
def socketio_domains_update(data):
    print('domain_update')
    socketio.emit('result',
                    app.isardapi.update_desktop_status(current_user.username, data),
                    namespace='/domains', 
                    room='user_'+current_user.username)


## Admin namespace
@socketio.on('connect', namespace='/admin_domains')
def socketio_domains_connect():
    #~ print('sid:'+request.sid)
    if current_user.role=='admin':
        join_room('admins')
        join_room('user_'+current_user.username)
        socketio.emit('user_quota', 
                        json.dumps(app.isardapi.get_user_quotas(current_user.username, current_user.quota)), 
                        namespace='/admin_domains', 
                        room='user_'+current_user.username)
    else:
        None
    
@socketio.on('disconnect', namespace='/domains')
def socketio_domains_disconnect():
    print('user:'+current_user.username+' disconnected')
    
## Main
if __name__ == '__main__':
    start_domains_thread()
    socketio.run(app,host='0.0.0.0', port=5000, debug=False)
