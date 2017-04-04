from gevent import monkey
monkey.patch_all()

import time
import json
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

socketio = SocketIO(app)
threads = {}

app.isardapi = api.isard()

import pprint

## Domains Threading
class DomainsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        with app.app_context():
            for c in r.table('domains').pluck('id','kind','hyp_started','name','description','icon','status','user').changes(include_initial=False).run(db.conn):
                #~ .without('xml','hardware','viewer')
                #~ pprint.pprint(c)
                if self.stop==True: break
                try:
                    if c['new_val'] is None:
                        if not c['old_val']['id'].startswith('_'): continue
                        data=c['old_val']
                        event='desktop_delete' if data['kind']=='desktop' else 'template_delete'
                    else:
                        if not c['new_val']['id'].startswith('_'): continue
                        data=c['new_val']
                        event='desktop_data' if data['kind']=='desktop' else 'template_data'
                    print('xxxxxxxxxxxxxxx DESKTOP '+data['id']+' STATUS: '+data['status'])
                    #~ pprint.pprint([ c['new_val'][x] for x in  c['old_val'] if x in c['new_val'] ])
                    socketio.emit(event, 
                                    json.dumps(app.isardapi.f.flatten_dict(data)), 
                                    namespace='/sio_users', 
                                    room='user_'+data['user'])
                    socketio.emit('user_quota', 
                                    json.dumps(app.isardapi.get_user_quotas(data['user'])), 
                                    namespace='/sio_users', 
                                    room='user_'+data['user'])
                    ## Admins should receive all updates on /admin namespace
                    socketio.emit(event, 
                                    json.dumps(app.isardapi.f.flatten_dict(data)), 
                                    namespace='/sio_admins', 
                                    room='domains')
                except Exception as e:
                    print('DomainsThread error:'+str(e))

def start_domains_thread():
    global threads
    if 'domains' not in threads: threads['domains']=None
    if threads['domains'] is None:
        threads['domains'] = DomainsThread()
        threads['domains'].daemon = True
        threads['domains'].start()
        print('DomainsThread Started')


## Domains Threading
class DomainsStatusThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        with app.app_context():
            for c in r.table('domains_status').pluck('name','when','status').changes(include_initial=False).run(db.conn):
                if self.stop==True: break
                try:
                    if c['new_val'] is not None:
                        if not c['new_val']['name'].startswith('_'): continue
                        socketio.emit('desktop_status', 
                                        json.dumps(app.isardapi.f.flatten_dict(c['new_val'])), 
                                        namespace='/sio_users', 
                                        room='user_'+c['new_val']['name'].split('_')[1])
                        ## Admins should receive all updates on /admin namespace
                        socketio.emit('desktop_status', 
                                        json.dumps(app.isardapi.f.flatten_dict(c['new_val'])), 
                                        namespace='/sio_admins', 
                                        room='domains_status')
                except Exception as e:
                    print('DomainsStatusThread error:'+str(e))

def start_domains_status_thread():
    global threads
    if 'domains_status' not in threads: threads['domains_status']=None
    if threads['domains_status'] is None:
        threads['domains_status'] = DomainsStatusThread()
        threads['domains_status'].daemon = True
        threads['domains_status'].start()
        print('DomainsStatusThread Started')
        
        
## Users Threading
class UsersThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        with app.app_context():
            for c in r.table('users').changes(include_initial=False).run(db.conn):
                if self.stop==True: break
                try:
                    if c['new_val'] is None:
                        data=c['old_val']
                        event='user_delete'
                    else:
                        data=c['new_val']
                        event='user_data'
                    socketio.emit(event, 
                                    json.dumps(app.isardapi.f.flatten_dict(data)), 
                                    namespace='/sio_users', 
                                    room='user_'+data['id'])
                    socketio.emit('user_quota', 
                                    json.dumps(app.isardapi.get_user_quotas(data['user'])), 
                                    namespace='/sio_users', 
                                    room='user_'+data['id'])
                    ## Admins should receive all updates on /admin namespace
                    socketio.emit(event, 
                                    json.dumps(app.isardapi.f.flatten_dict(data)), 
                                    namespace='/sio_admins', 
                                    room='users')
                except Exception as e:
                    print('UsersThread error:'+str(e))

def start_users_thread():
    global threads
    if 'users' not in threads: threads['users']=None
    if threads['users'] is None:
        threads['users'] = UsersThread()
        threads['users'].daemon = True
        threads['users'].start()
        print('UsersThread Started')       

## Domains namespace
@socketio.on('connect', namespace='/sio_users')
def socketio_users_connect():
    #~ print('sid:'+request.sid)
    join_room('user_'+current_user.username)
    socketio.emit('user_quota', 
                    json.dumps(app.isardapi.get_user_quotas(current_user.username, current_user.quota)), 
                    namespace='/sio_users', 
                    room='user_'+current_user.username)
    
@socketio.on('disconnect', namespace='/sio_users')
def socketio_domains_disconnect():
    print('user:'+current_user.username+' disconnected')

@socketio.on('domain_update', namespace='/sio_users')
def socketio_domains_update(data):
    socketio.emit('result',
                    app.isardapi.update_desktop_status(current_user.username, data),
                    namespace='/sio_users', 
                    room='user_'+current_user.username)

@socketio.on('domain_viewer', namespace='/sio_users')
def socketio_domains_viewer(data):
    if data['kind'] == 'file':
        consola=app.isardapi.get_spice_ticket(data['pk'])
        viewer=''
        #~ return Response(consola, 
                        #~ mimetype="application/x-virt-viewer",
                        #~ headers={"Content-Disposition":"attachment;filename=consola.vv"})
    if data['kind'] == 'xpi':
        viewer=app.isardapi.get_spice_xpi(data['pk'])

    if data['kind'] == 'html5':
        print('HTML5')
        viewer=app.isardapi.get_domain_spice(data['pk'])
        ##### Change this when engine opens ports accordingly (without tls)
        if viewer['port'] or True:
            #~ dict['port'] = "5"+ dict['port']
            viewer['port'] = viewer['port'] if viewer['port'] else viewer['tlsport']
            viewer['port'] = "5"+ viewer['port']
            
    socketio.emit('domain_viewer',
                    json.dumps({'kind':data['kind'],'viewer':viewer}),
                    namespace='/sio_users', 
                    room='user_'+current_user.username)




## Admin namespace
@socketio.on('connect', namespace='/sio_admins')
def socketio_admins_connect():
    #~ print('sid:'+request.sid)
    if current_user.role=='admin':
        join_room('admins')
        join_room('user_'+current_user.username)
        socketio.emit('user_quota', 
                        json.dumps(app.isardapi.get_user_quotas(current_user.username, current_user.quota)), 
                        namespace='/sio_admins', 
                        room='user_'+current_user.username)
    else:
        None

@socketio.on('join_rooms', namespace='/sio_admins')
def socketio_admins_connect(join_rooms):
    #~ print('sid:'+request.sid)
    if current_user.role=='admin':
        for rm in join_rooms:
            join_room(rm)
            
@socketio.on('disconnect', namespace='/sio_admins')
def socketio_admins_disconnect():
    leave_room('admins')
    leave_room('user_'+current_user.username)
    print('admin user:'+current_user.username+' disconnected')
    
## Main
if __name__ == '__main__':
    start_domains_thread()
    start_domains_status_thread()
    start_users_thread()
    
    import logging
    logger=logging.getLogger("socketio")
    #~ level = logging.getLevelName('ERROR')
    logger.setLevel('ERROR')
    engineio_logger=logging.getLogger("engineio")
    engineio_logger.setLevel('ERROR')
    socketio.run(app,host='0.0.0.0', port=5000, debug=False, logger=logger, engineio_logger=engineio_logger)
