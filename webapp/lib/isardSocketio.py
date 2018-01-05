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

from ..lib.log import *

import rethinkdb as r
from ..lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

#~ from .decorators import ownsid
from webapp import app
socketio = SocketIO(app)
threads = {}

## Domains Threading
class DomainsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        with app.app_context():
            for c in r.table('domains').without('xml','hardware','viewer').changes(include_initial=False).run(db.conn):
                #~ .pluck('id','kind','hyp_started','name','description','icon','status','user')
                if self.stop==True: break
                try:
                    if c['new_val'] is None:
                        if not c['old_val']['id'].startswith('_'): continue
                        data=c['old_val']
                        event='desktop_delete' if data['kind']=='desktop' else 'template_delete'
                    else:
                        if not c['new_val']['id'].startswith('_'): continue
                        data=c['new_val']   
                        if data['kind']=='desktop':
                            event='desktop_data'
                        else:
                            event='template_data'
                            data['derivates']=app.adminapi.get_admin_domains_with_derivates(id=c['new_val']['id'],kind='template')
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
                    log.error('DomainsThread error:'+str(e))

def start_domains_thread():
    global threads
    if 'domains' not in threads: threads['domains']=None
    if threads['domains'] is None:
        threads['domains'] = DomainsThread()
        threads['domains'].daemon = True
        threads['domains'].start()
        log.info('DomainsThread Started')

            
## Domains Stats Threading
class DomainsStatsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False
        self.domains= dict()

    def run(self):
        with app.app_context():
            for c in r.table('domains_status').pluck('name','when','status').merge({'table':'stats'}).changes(include_initial=False).union(
                    r.table('domains').get_all(r.args(['Started','Stopping','Stopped']),index='status').pluck('id','name','os','hyp_started','status').merge({"table": "domains"}).changes(include_initial=False)).run(db.conn):
                if self.stop==True: break
                #~ import pprint
                #~ pprint.pprint(c)
                try:
                    if c['new_val'] is not None:
                        if not c['new_val']['name'].startswith('_'): continue
                        if c['new_val']['name'] not in self.domains.keys():
                            if r.table('domains').get(c['new_val']['name']).run(db.conn) is None: continue
                            domain=r.table('domains').get(c['new_val']['name']).pluck('id','name','status','hyp_started','os').run(db.conn)
                            self.domains[c['new_val']['name']]=domain
                        else:
                            domain=self.domains[c['new_val']['name']]
                        if domain is not None: #This if can be removed when vimet is shutdown
                                new_dom=domain.copy()
                                if domain['status']=='Started':
                                    new_dom['status']=c['new_val']['status']
                                    socketio.emit('desktop_status', 
                                                    json.dumps(new_dom), 
                                                    namespace='/sio_users', 
                                                    room='user_'+c['new_val']['name'].split('_')[1])
                                    socketio.emit('desktop_status', 
                                                    json.dumps(new_dom), 
                                                    namespace='/sio_admins', 
                                                    room='domains_status')

                                else:
                                    self.domains.pop(c['new_val']['name'],None)
                                    socketio.emit('desktop_stopped', 
                                                    json.dumps(new_dom), 
                                                    namespace='/sio_admins', 
                                                    room='domains_status')
                                new_dom=None
                except Exception as e:
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    log.error(exc_type, fname, exc_tb.tb_lineno)
                    log.error('DomainsStatusThread error:'+str(e))

def start_domains_stats_thread():
    global threads

    if 'domains_stats' not in threads: threads['domains_stats']=None
    if threads['domains_stats'] is None:
        threads['domains_stats'] = DomainsStatsThread()
        threads['domains_stats'].daemon = True
        threads['domains_stats'].start()
        log.info('DomainsStatsThread Started')
        

## MEDIA Threading
class MediaThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        with app.app_context():
            for c in r.table('media').changes(include_initial=False).run(db.conn):
                #~ .pluck('id','percentage')
                if self.stop==True: break
                try:
                    if c['new_val'] is None:
                        #~ if not c['old_val']['id'].startswith('_'): continue
                        data=c['old_val']
                        event='media_delete'
                    else:
                        #~ if not c['new_val']['id'].startswith('_'): continue
                        
                        data=c['new_val']
                        event='media_data'
                    #~ socketio.emit(event, 
                                    #~ json.dumps(app.isardapi.f.flatten_dict(data)), 
                                    #~ namespace='/sio_users', 
                                    #~ room='user_'+data['user'])
                    #~ socketio.emit('user_quota', 
                                    #~ json.dumps(app.isardapi.get_user_quotas(data['user'])), 
                                    #~ namespace='/sio_users', 
                                    #~ room='user_'+data['user'])
                    ## Admins should receive all updates on /admin namespace
                    socketio.emit(event, 
                                    json.dumps(app.isardapi.f.flatten_dict(data)), 
                                    namespace='/sio_admins', 
                                    room='media')
                except Exception as e:
                    log.error('MediaThread error:'+str(e))

def start_media_thread():
    global threads
    if 'media' not in threads: threads['media']=None
    if threads['media'] is None:
        threads['media'] = MediaThread()
        threads['media'].daemon = True
        threads['media'].start()
        log.info('MediaThread Started')
        
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
                    log.error('UsersThread error:'+str(e))

def start_users_thread():
    global threads
    if 'users' not in threads: threads['users']=None
    if threads['users'] is None:
        threads['users'] = UsersThread()
        threads['users'].daemon = True
        threads['users'].start()
        log.info('UsersThread Started')       

## Hypervisors Threading
class HypervisorsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        with app.app_context():
            for c in r.table('hypervisors').merge({"table": "hyper"}).changes(include_initial=False).union(
                        r.table('hypervisors_status').pluck('hyp_id','domains',{'cpu_percent':{'used'}},{'load':{'percent_free'}}).merge({"table": "hyper_status"}).changes(include_initial=False)).run(db.conn):
                        #~ .union(
                        #~ r.table('domains').get_all(r.args(['Started','Stopping','Stopped']),index='status').pluck('id','name','hyp_started','status').merge({"table": "domains"}).changes(include_initial=False)).run(db.conn):
                if self.stop==True: break
                try:
                    if c['new_val'] is None:
                        if c['old_val']['table']=='hyper':
                            socketio.emit('hyper_deleted', 
                                            json.dumps(c['old_val']['id']), 
                                            namespace='/sio_admins', 
                                            room='hyper')                           
                    else:
                        if c['new_val']['table']=='hyper': event='hyper_data'
                        if c['new_val']['table']=='hyper_status': 
                            event='hyper_status'
                            c['new_val']['domains']=len(c['new_val']['domains'])
                            c['new_val']['cpu_percent']['used']=round(c['new_val']['cpu_percent']['used'])
                            c['new_val']['load']['percent_free']=round(c['new_val']['load']['percent_free'])
                        #~ if c['new_val']['table']=='domains' and c['new_val']['id'].startswith('_') : 
                            #~ if c['new_val']['status'] == 'Stopping': continue
                            #~ event='domain_event'
                            #~ if c['new_val']['status']=='Stopped': c['new_val']['hyp_started']=c['old_val']['hyp_started']
                        socketio.emit(event, 
                                        json.dumps(app.isardapi.f.flatten_dict(c['new_val'])), 
                                        namespace='/sio_admins', 
                                        room='hyper')  
                except Exception as e:
                    log.error('HypervisorsThread error:'+str(e))
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    log.error(exc_type, fname, exc_tb.tb_lineno)
                    
def start_hypervisors_thread():
    global threads
    if 'hypervisors' not in threads: threads['hypervisors']=None
    if threads['hypervisors'] is None:
        threads['hypervisors'] = HypervisorsThread()
        threads['hypervisors'].daemon = True
        threads['hypervisors'].start()
        log.info('HypervisorsThread Started')  

## Config Threading
class ConfigThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        with app.app_context():
            for c in r.table('backups').merge({'table':'backups'}).changes(include_initial=False).union(
                r.table('scheduler_jobs').without('job_state').merge({'table':'scheduler_jobs'}).changes(include_initial=False)).run(db.conn):
                if self.stop==True: break
                try:
                    if c['new_val'] is None:
                        event= 'backup_deleted' if c['old_val']['table']=='backups' else 'sch_deleted'
                        socketio.emit(event, 
                                        json.dumps(c['old_val']), 
                                        namespace='/sio_admins', 
                                        room='config')
                    else:
                        event='backup_data' if c['new_val']['table']=='backups' else 'sch_data'
                        if event=='sch_data' and 'name' not in c['new_val'].keys():
                            continue
                        socketio.emit(event, 
                                        json.dumps(c['new_val']),
                                        namespace='/sio_admins', 
                                        room='config') 
                except Exception as e:
                    log.error('ConfigThread error:'+str(e))
                    
def start_config_thread():
    global threads
    if 'config' not in threads: threads['config']=None
    if threads['config'] is None:
        threads['config'] = ConfigThread()
        threads['config'].daemon = True
        threads['config'].start()
        log.info('ConfigThread Started')

## Domains namespace
@socketio.on('connect', namespace='/sio_users')
def socketio_users_connect():
    join_room('user_'+current_user.username)
    socketio.emit('user_quota', 
                    json.dumps(app.isardapi.get_user_quotas(current_user.username, current_user.quota)), 
                    namespace='/sio_users', 
                    room='user_'+current_user.username)
    
@socketio.on('disconnect', namespace='/sio_users')
def socketio_domains_disconnect():
    log.debug('USER: '+current_user.username+' DISCONNECTED')

@socketio.on('domain_update', namespace='/sio_users')
def socketio_domains_update(data):
    remote_addr=request.headers['X-Forwarded-For'] if 'X-Forwarded-For' in request.headers else request.remote_addr
    socketio.emit('result',
                    app.isardapi.update_table_status(current_user.username, 'domains', data,remote_addr),
                    namespace='/sio_users', 
                    room='user_'+current_user.username)

@socketio.on('media_update', namespace='/sio_users')
def socketio_media_update(data):
    remote_addr=request.headers['X-Forwarded-For'] if 'X-Forwarded-For' in request.headers else request.remote_addr
    socketio.emit('result',
                    app.isardapi.update_table_status(current_user.username, 'media', data,remote_addr),
                    namespace='/sio_users', 
                    room='user_'+current_user.username)
                    
@socketio.on('domain_viewer', namespace='/sio_users')
def socketio_domains_viewer(data):
    #~ if data['kind'] == 'file':
        #~ consola=app.isardapi.get_viewer_ticket(data['pk'])
        #~ viewer=''
        #~ return Response(consola, 
                        #~ mimetype="application/x-virt-viewer",
                        #~ headers={"Content-Disposition":"attachment;filename=consola.vv"})
    if data['kind'] == 'xpi':
        viewer=app.isardapi.get_spice_xpi(data['pk'])

    if data['kind'] == 'html5':
        viewer=app.isardapi.get_domain_spice(data['pk'])
        ##### Change this when engine opens ports accordingly (without tls)
        if viewer['port']:
            viewer['port'] = viewer['port'] if viewer['port'] else viewer['tlsport']
            viewer['port'] = "5"+ viewer['port']
        #~ viewer['port']=viewer['port']-1
    socketio.emit('domain_viewer',
                    json.dumps({'kind':data['kind'],'viewer':viewer}),
                    namespace='/sio_users', 
                    room='user_'+current_user.username)

@socketio.on('domain_add', namespace='/sio_users')
def socketio_domains_add(form_data):
    #~ Check if user has quota and rights to do it
    #~ if current_user.role=='admin':
        #~ None
    create_dict=app.isardapi.f.unflatten_dict(form_data)
    create_dict=parseHardware(create_dict)
    res=app.isardapi.new_domain_from_tmpl(current_user.username, create_dict)

    if res is True:
        data=json.dumps({'result':True,'title':'New desktop','text':'Desktop '+create_dict['name']+' is being created...','icon':'success','type':'success'})
    else:
        data=json.dumps({'result':True,'title':'New desktop','text':'Desktop '+create_dict['name']+' can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    data,
                    namespace='/sio_users', 
                    room='user_'+current_user.username)

@socketio.on('domain_edit', namespace='/sio_users')
def socketio_domain_edit(form_data):
    #~ Check if user has quota and rights to do it
    #~ if current_user.role=='admin':
        #~ None
    create_dict=app.isardapi.f.unflatten_dict(form_data)
    create_dict=parseHardware(create_dict)
    create_dict['create_dict']={'hardware':create_dict['hardware'].copy()}
    create_dict.pop('hardware',None)
    res=app.isardapi.update_domain(create_dict.copy())
    if res is True:
        data=json.dumps({'id':create_dict['id'], 'result':True,'title':'Updated desktop','text':'Desktop '+create_dict['name']+' has been updated...','icon':'success','type':'success'})
    else:
        data=json.dumps({'id':create_dict['id'], 'result':True,'title':'Updated desktop','text':'Desktop '+create_dict['name']+' can\'t be updated.','icon':'warning','type':'error'})
    socketio.emit('edit_form_result',
                    data,
                    namespace='/sio_users', 
                    room='user_'+current_user.username)

@socketio.on('domain_edit', namespace='/sio_admins')
def socketio_admins_domain_edit(form_data):
    #~ Check if user has quota and rights to do it
    #~ if current_user.role=='admin':
        #~ None
    create_dict=app.isardapi.f.unflatten_dict(form_data)
    create_dict=parseHardware(create_dict)
    create_dict['create_dict']={'hardware':create_dict['hardware'].copy()}
    create_dict.pop('hardware',None)
    res=app.isardapi.update_domain(create_dict.copy())
    if res is True:
        data=json.dumps({'id':create_dict['id'], 'result':True,'title':'Updated desktop','text':'Desktop '+create_dict['name']+' has been updated...','icon':'success','type':'success'})
    else:
        data=json.dumps({'id':create_dict['id'], 'result':True,'title':'Updated desktop','text':'Desktop '+create_dict['name']+' can\'t be updated.','icon':'warning','type':'error'})
    socketio.emit('edit_form_result',
                    data,
                    namespace='/sio_admins', 
                    room='domains')
                    
def parseHardware(create_dict):
    if 'hardware' not in create_dict.keys():
        #~ Hardware is not in create_dict
        data=app.isardapi.get_domain(create_dict['template'], human_size=False, flatten=False)
        create_dict['hardware']=data['create_dict']['hardware']
        create_dict['hardware'].pop('disks',None)
        create_dict['hypervisors_pools']=data['hypervisors_pools']
    else:
        if create_dict['hardware']['vcpus']=='':
            data=app.isardapi.get_domain(create_dict['template'], human_size=False, flatten=False)
            create_dict['hardware']['vcpus']=data['hardware']['vcpus']
            create_dict['hardware']['memory']=data['hardware']['memory']/1024
        create_dict['hypervisors_pools']=[create_dict['hypervisors_pools']]
        create_dict['hardware']['boot_order']=[create_dict['hardware']['boot_order']]
        create_dict['hardware']['graphics']=[create_dict['hardware']['graphics']]
        create_dict['hardware']['videos']=[create_dict['hardware']['videos']]
        create_dict['hardware']['interfaces']=[create_dict['hardware']['interfaces']]
        create_dict['hardware']['memory']=int(create_dict['hardware']['memory'])*1024
    return create_dict

@socketio.on('media_add', namespace='/sio_users')
def socketio_media_add(form_data):
    filename = form_data['url'].split('/')[-1]
    media=app.isardapi.user_relative_media_path(current_user.username, filename)
    if not media:
        data=json.dumps({'result':True,'title':'New desktop','text':'Desktop '+create_dict['name']+' can\'t be created. It doesn\'t seem a valid url filename.','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/sio_users', 
                        room='user_'+current_user.username)
    else:
        #dict = {**form_data, **iso}
        dict = {}
        dict['status']='Starting'
        dict['percentage']=0
        res = app.isardapi.add_dict2table(dict,'media')
        if res is True:
            data=json.dumps({'result':True,'title':'New media','text':'Media '+media['name']+' is being uploaded...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':True,'title':'New media','text':'Media '+media['name']+' can\'t be uploaded. You have the same media filename uploaded already.','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/sio_users', 
                        room='user_'+current_user.username)

## Admin namespace
@socketio.on('connect', namespace='/sio_admins')
def socketio_admins_connect():
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
    if current_user.role=='admin':
        for rm in join_rooms:
            join_room(rm)
            log.debug('USER: '+current_user.username+' JOINED ROOM: '+rm)

@socketio.on('get_tree_list', namespace='/sio_admins')
def socketio_get_tree_list():
    socketio.emit('tree_list',
                    app.isardapi.app.adminapi.get_domains_tree_list(),
                    namespace='/sio_admins', 
                    room='user_'+current_user.username)

@socketio.on('domain_virtbuilder_add', namespace='/sio_admins')
def socketio_domains_virtualbuilder_add(form_data):
    create_dict=app.isardapi.f.unflatten_dict(form_data)
    create_dict['hardware']['boot_order']=[create_dict['hardware']['boot_order']]
    create_dict['hardware']['graphics']=[create_dict['hardware']['graphics']]
    create_dict['hardware']['videos']=[create_dict['hardware']['videos']]
    create_dict['hardware']['interfaces']=[create_dict['hardware']['interfaces']]
    create_dict['hardware']['memory']=int(create_dict['hardware']['memory'])*1024
    create_dict['hardware']['vcpus']=create_dict['hardware']['vcpus']
    disk_size=create_dict['disk_size']+'G'
    create_dict.pop('disk_size',None)
    name=create_dict['name']
    create_dict.pop('name',None)
    description=create_dict['description']
    create_dict.pop('description',None)
    hyper_pools=[create_dict['hypervisors_pools']]
    create_dict.pop('hypervisors_pools',None)
    icon=create_dict['icon']
    create_dict.pop('icon',None)
    create_dict['builder']['options']=create_dict['builder']['options'].replace('\r\n','')
    res=app.adminapi.new_domain_from_virtbuilder(current_user.username, name, description, icon, create_dict, hyper_pools, disk_size)
    if res is True:
        data=json.dumps({'result':True,'title':'New desktop','text':'Desktop '+name+' is being created...','icon':'success','type':'success'})
    else:
        data=json.dumps({'result':True,'title':'New desktop','text':'Desktop '+name+' can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    data,
                    namespace='/sio_admins', 
                    room='user_'+current_user.username)

@socketio.on('domain_virtiso_add', namespace='/sio_admins')
def socketio_domains_virtualiso_add(form_data):
    log.debug(form_data)
    
@socketio.on('classroom_update', namespace='/sio_admins')
def socketio_classroom_update(data):
    if app.adminapi.replace_hosts_viewers_items(data['place'],data['hosts']):
        result=json.dumps({'title':'Desktop starting success','text':'Aula will be started','icon':'success','type':'info'}), 200, {'ContentType':'application/json'}
    else:
        result=json.dumps({'title':'Desktop starting error','text':'Aula can\'t be started now','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
    socketio.emit('result',
                    result,
                    namespace='/sio_admins', 
                    room='user_'+current_user.username)

@socketio.on('classroom_get', namespace='/sio_admins')
def socketio_classroom_update(data):
    #~ if app.adminapi.get_hosts_viewers(data['place_id']):
        #~ result=json.dumps({'title':'Desktop starting success','text':'Aula will be started','icon':'success','type':'info'}), 200, {'ContentType':'application/json'}
    #~ else:
        #~ result=json.dumps({'title':'Desktop starting error','text':'Aula can\'t be started now','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
    #~ print(data)
    #~ print(app.adminapi.get_hosts_viewers(data['place_id']))
    socketio.emit('classroom_load',
                    json.dumps({'place': app.adminapi.get_admin_table('places',id=data['place_id']) ,'hosts':app.adminapi.get_hosts_viewers(data['place_id'])}),
                    namespace='/sio_admins', 
                    room='user_'+current_user.username)


@socketio.on('scheduler_add', namespace='/sio_admins')
def socketio_scheduler_add(form_data):

#~ {'action': 'delete_old_stats',
 #~ 'hour': '00',
 #~ 'kind': 'cron',
 #~ 'minute': '00',
 #~ 'older': ''}
#~ {'action': 'delete_old_stats',
 #~ 'hour': '00',
 #~ 'kind': 'cron',
 #~ 'minute': '00',
 #~ 'older': ''}
    res=app.scheduler.add_scheduler(form_data['kind'],form_data['action'],form_data['hour'],form_data['minute'])  
    if res is True:
        data=json.dumps({'result':True,'title':'New scheduler','text':'Scheduler is being created...','icon':'success','type':'success'})
    else:
        data=json.dumps({'result':True,'title':'New scheduler','text':'Scheduler can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    data,
                    namespace='/sio_admins', 
                    room='config')

                    
@socketio.on('disconnect', namespace='/sio_admins')
def socketio_admins_disconnect():
    leave_room('admins')
    leave_room('user_'+current_user.username)
    log.debug('USER: '+current_user.username+' DISCONNECTED')
    

