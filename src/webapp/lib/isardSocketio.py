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

from .isardViewer import isardViewer
isardviewer = isardViewer()

socketio = SocketIO(app)
threads = {}

## Domains Threading
class DomainsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        starteddict={}
        with app.app_context():
            for c in r.table('domains').without('xml','history_domain').changes(include_initial=False).run(db.conn):
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
                        # ~ data['accessed']=time.time()
                          
                        ''' Disposables on login '''
                        # ~ if data['user']=='disposable':
                            # ~ # print('im a disposable: '+data['id'])
                            # ~ event='desktop_data'
                            # ~ socketio.emit(event, 
                                            # ~ json.dumps(app.isardapi.f.flatten_dict(data)), 
                                            # ~ namespace='/sio_admins', 
                                            # ~ room='domains')   
                                                                       
                            # ~ ip=data['name'].replace('_','.')
                            # ~ # try:
                                # ~ # ip=data['viewer']['client_addr']
                            # ~ # except Exception as e:
                                # ~ # # print(data['id']+' is disposable but has no viewer client addr')
                                # ~ # continue
                            # ~ # if ip:
                                # ~ # print('EMITTED DISPOSABLE DATA')
                            # ~ # print('old: '+c['old_val']['status']+' new: '+c['new_val']['status'])
                            # ~ # if 'viewer' in c['new_val']:
                                # ~ # print(c['new_val'])
                            # ~ if data['status']=='Started' and c['old_val']['status']!='Started': # and data['detail']=='':
                                # ~ # if starteddict=={}:
                                    # ~ # starteddict=data
                                    # ~ # starteddict['detail']='hander'
                                # ~ # else:
                                    # ~ # import pprint
                                    # ~ # pprint.pprint( dict(set(starteddict) ^ set(data)))
                                # ~ # print('old: '+c['old_val']['status']+' new: '+c['new_val']['status'])
                                # ~ socketio.emit('disposable_data', 
                                                    # ~ json.dumps(app.isardapi.f.flatten_dict({'id':data['id'],'status':data['status']})), 
                                                    # ~ namespace='/sio_disposables', 
                                                    # ~ room='disposable_'+ip)                                        
                            # ~ continue
                        ''' End disposables '''
                        
                        if data['kind']=='desktop':
                            event='desktop_data'
                        else:
                            event='template_data'
                            data['derivates']=app.adminapi.get_admin_domains_with_derivates(id=c['new_val']['id'],kind='template')
                            data['kind']=app.isardapi.get_template_kind(data['user'],data)
                    socketio.emit(event, 
                                    json.dumps(data), 
                                    #~ json.dumps(app.isardapi.f.flatten_dict(data)), 
                                    namespace='/sio_users', 
                                    room='user_'+data['user'])
                    socketio.emit('user_quota', 
                                    json.dumps(app.isardapi.get_user_quotas(data['user'])), 
                                    namespace='/sio_users', 
                                    room='user_'+data['user'])
                    ## Admins should receive all updates on /admin namespace
                    socketio.emit(event, 
                                    json.dumps(data),
                                    #~ json.dumps(app.isardapi.f.flatten_dict(data)), 
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
            for c in r.table('domains').get_all(r.args(['Downloaded', 'DownloadFailed','DownloadStarting', 'Downloading', 'DownloadAborting','ResetDownloading']),index='status').pluck('id','name','description','icon','progress','status','user').merge({'table':'domains'}).changes(include_initial=False).union(
                    r.table('media').get_all(r.args(['Deleting', 'Deleted', 'Downloaded', 'DownloadFailed', 'DownloadStarting', 'Downloading', 'Download', 'DownloadAborting','ResetDownloading']),index='status').merge({'table':'media'}).changes(include_initial=False)).run(db.conn):
                if self.stop==True: break
                try:
                    if c['new_val'] is None:
                        data=c['old_val']
                        event=c['old_val']['table']+'_delete'
                    else:
                        data=c['new_val']
                        event=c['new_val']['table']+'_data'
                    ## Admins should receive all updates on /admin namespace
                    ## Users should receive not only their media updates, also the shared one's with them!
                    socketio.emit(event, 
                                    json.dumps(data), 
                                    namespace='/sio_users', 
                                    room='user_'+data['user'])
                    socketio.emit('user_quota', 
                                    json.dumps(app.isardapi.get_user_quotas(data['user'])), 
                                    namespace='/sio_users', 
                                    room='user_'+data['user'])                    
                    socketio.emit(event, 
                                    json.dumps(data),
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



## MEDIA Threading
class ResourcesThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        with app.app_context():
            for c in r.table('graphics').merge({'table':'graphics'}).changes(include_initial=False).union(
                    r.table('videos').merge({'table':'videos'}).changes(include_initial=False).union(
                    r.table('interfaces').merge({'table':'interfaces'}).changes(include_initial=False).union(
                    r.table('boots').merge({'table':'boots'}).changes(include_initial=False)))).run(db.conn):
                if self.stop==True: break
                try:
                    if c['new_val'] is None:
                        data={'table':c['old_val']['table'],'data':c['old_val']}
                        event='delete'
                    else:
                        data={'table':c['new_val']['table'],'data':c['new_val']}
                        event='data'
                    ## Admins should receive all updates on /admin namespace                  
                    socketio.emit(event, 
                                    json.dumps(data), #app.isardapi.f.flatten_dict(data)), 
                                    namespace='/sio_admins', 
                                    room='resources')                                  
                except Exception as e:
                    log.error('MediaThread error:'+str(e))

def start_resources_thread():
    global threads
    if 'resources' not in threads: threads['resources']=None
    if threads['resources'] is None:
        threads['resources'] = ResourcesThread()
        threads['resources'].daemon = True
        threads['resources'].start()
        log.info('ResourcesThread Started')    
            
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
                                    json.dumps(app.isardapi.get_user_quotas(data['id'])), 
                                    namespace='/sio_users', 
                                    room='user_'+data['id'])
                    ## Admins should receive all updates on /admin namespace
                    socketio.emit(event, 
                                    json.dumps(app.isardapi.f.flatten_dict(data)), 
                                    namespace='/sio_admins', 
                                    room='users')
                except Exception as e:
                    log.error('UsersThread error:'+str(e))
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    log.error(exc_type, fname, exc_tb.tb_lineno)

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
                            c['new_val']['cpu_percent']['used']=0    #round(c['new_val']['cpu_percent']['used'])
                            c['new_val']['load']['percent_free']=100   #round(c['new_val']['load']['percent_free'])
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
                    #~ exc_type, exc_obj, exc_tb = sys.exc_info()
                    #~ fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    #~ log.error(exc_type, fname, exc_tb.tb_lineno)
                    
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
                r.table('scheduler_jobs').has_fields('name').without('job_state').merge({'table':'scheduler_jobs'}).changes(include_initial=False)).union(
                r.table('disposables').merge({'table':'disposables'}).changes(include_initial=False)).run(db.conn):
                if self.stop==True: break
                try:
                    if c['new_val'] is None:
                        event= '_deleted'
                        socketio.emit(c['old_val']['table']+event, 
                                        json.dumps(c['old_val']), 
                                        namespace='/sio_admins', 
                                        room='config')
                    else:
                        event= '_data'
                        socketio.emit(c['new_val']['table']+event, 
                                        json.dumps(c['new_val']),
                                        namespace='/sio_admins', 
                                        room='config') 
                                                                
                        #~ event= 'backup_deleted' if c['old_val']['table']=='backups' else 'sch_deleted'
                        #~ socketio.emit(event, 
                                        #~ json.dumps(c['old_val']), 
                                        #~ namespace='/sio_admins', 
                                        #~ room='config')
                    #~ else:
                        #~ event='backup_data' if c['new_val']['table']=='backups' else 'sch_data'
                        #~ if event=='sch_data' and 'name' not in c['new_val'].keys():
                            #~ continue
                        #~ socketio.emit(event, 
                                        #~ json.dumps(c['new_val']),
                                        #~ namespace='/sio_admins', 
                                        #~ room='config') 
                except Exception as e:
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    log.error(exc_type, fname, exc_tb.tb_lineno)
                    log.error('ConfigThread error:'+str(e))
                    
def start_config_thread():
    global threads
    if 'config' not in threads: threads['config']=None
    if threads['config'] is None:
        threads['config'] = ConfigThread()
        threads['config'].daemon = True
        threads['config'].start()
        log.info('ConfigThread Started')


## Hypervisors namespace

@socketio.on('hyper_add', namespace='/sio_admins')
def socketio_hyper_add(form_data):
    if current_user.role == 'admin': 
        create_dict=app.isardapi.f.unflatten_dict(form_data)
        if 'capabilities' not in create_dict: create_dict['capabilities']={}
        if 'disk_operations' not in create_dict['capabilities']:
            create_dict['capabilities']['disk_operations']=False
        else:
            create_dict['capabilities']['disk_operations']=True
        if 'hypervisor' not in create_dict['capabilities']:
            create_dict['capabilities']['hypervisor']=False
        else:
            create_dict['capabilities']['hypervisor']=True
        if create_dict['capabilities']['disk_operations'] or create_dict['capabilities']['hypervisor']:
            # NOTE: Should be changed if multiple select instead of select
            create_dict['hypervisors_pools']=[create_dict['hypervisors_pools']]
            create_dict['detail']=''
            create_dict['info']=[]
            create_dict['prev_status']=''
            create_dict['status']='New'
            create_dict['status_time']=''
            create_dict['uri']=''
            create_dict['enabled']=True
            res=app.adminapi.hypervisor_add(create_dict)

            if res is True:
                info=json.dumps({'result':True,'title':'New hypervisor','text':'Hypervisor '+create_dict['hostname']+' has been created.','icon':'success','type':'success'})
                ### Engine restart needed
                
                ### Warning
            else:
                info=json.dumps({'result':False,'title':'New hypervisor','text':'Hypervisor '+create_dict['hostname']+' can\'t be created. Maybe it already exists!','icon':'warning','type':'error'})
            socketio.emit('add_form_result',
                            info,
                            namespace='/sio_admins', 
                            room='hyper')
        else:
            info=json.dumps({'result':False,'title':'Hypervisor add error','text':'Hypervisor should have at least one capability!','icon':'warning','type':'error'})        
            socketio.emit('result',
                            info,
                            namespace='/sio_admins', 
                            room='hyper')            

@socketio.on('hyper_edit', namespace='/sio_admins')
def socketio_hyper_edit(form_data):
    if current_user.role == 'admin': 
        create_dict=app.isardapi.f.unflatten_dict(form_data)
        
        if 'capabilities' not in create_dict: create_dict['capabilities']={}
        if 'disk_operations' not in create_dict['capabilities']:
            create_dict['capabilities']['disk_operations']=False
        else:
            create_dict['capabilities']['disk_operations']=True
        if 'hypervisor' not in create_dict['capabilities']:
            create_dict['capabilities']['hypervisor']=False
        else:
            create_dict['capabilities']['hypervisor']=True
            
        if create_dict['capabilities']['disk_operations'] or create_dict['capabilities']['hypervisor']:
            # NOTE: Should be changed if multiple select instead of select
            create_dict['hypervisors_pools']=[create_dict['hypervisors_pools']]
            create_dict['detail']=''
            create_dict['info']=[]
            #~ create_dict['prev_status']=''
            #~ create_dict['status']='Updating'
            create_dict['status_time']=''
            create_dict['uri']=''
            #~ create_dict['enabled']=True
            res=app.adminapi.hypervisor_edit(create_dict)

            if res is True:
                info=json.dumps({'result':True,'title':'Edit hypervisor','text':'Hypervisor '+create_dict['hostname']+' has been edited.','icon':'success','type':'success'})
                ### Engine restart needed
                
                ### Warning
            else:
                info=json.dumps({'result':False,'title':'Edit hypervisor','text':'Hypervisor '+create_dict['hostname']+' can\'t be edited now.','icon':'warning','type':'error'})
            socketio.emit('add_form_result',
                            info,
                            namespace='/sio_admins', 
                            room='hyper')
        else:
            info=json.dumps({'result':False,'title':'Hypervisor edit error','text':'Hypervisor should have at least one capability!','icon':'warning','type':'error'})        
            socketio.emit('result',
                            info,
                            namespace='/sio_admins', 
                            room='hyper') 

@socketio.on('hyper_delete', namespace='/sio_admins')
def socketio_hyper_delete(data):
    if current_user.role == 'admin': 
        # ~ remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
        res=app.adminapi.hypervisor_delete(data['pk'])
        # ~ res=app.adminapi.update_table_dict('hypervisors',data['pk'],{'enabled':False,'status':'Deleting'}),
        if res is True:
            info=json.dumps({'result':True,'title':'Hypervisor deletiing','text':'Hypervisor '+data['name']+' deletion on progress. Engine will delete it when no operations pending.','icon':'success','type':'success'})
        else:
            info=json.dumps({'result':False,'title':'Hypervisor deleting','text':'Hypervisor '+data['name']+' could not set it to start deleting process.','icon':'warning','type':'error'})          
        socketio.emit('result',
                        info,
                        namespace='/sio_admins', 
                        room='hyper')

@socketio.on('hyper_toggle', namespace='/sio_admins')
def socketio_hyper_toggle(data):
    if current_user.role == 'admin': 
        # ~ remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
        res=app.adminapi.hypervisor_toggle_enabled(data['pk'])
        if res is True:
            info=json.dumps({'result':True,'title':'Hypervisor enable/disable','text':'Hypervisor '+data['name']+' enable/disable success.','icon':'success','type':'success'})
        else:
            info=json.dumps({'result':False,'title':'Hypervisor enable/disable','text':'Hypervisor '+data['name']+' could not toggle enable status!','icon':'warning','type':'error'})        
        socketio.emit('result',
                        info,
                        namespace='/sio_admins', 
                        room='hyper')

@socketio.on('hyper_domains_stop', namespace='/sio_admins')
def socketio_hyper_domains_stop(data):
    if current_user.role == 'admin': 
        # ~ remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
        res=app.adminapi.domains_stop(hyp_id=data['pk'],without_viewer=data['without_viewer'])
        if res is False:
            info=json.dumps({'result':False,'title':'Hypervisor domains stoping','text':'Domains in '+data['name']+' hypervisor could not be stopped now.!','icon':'warning','type':'error'}) 
            
        else:
            info=json.dumps({'result':True,'title':'Hypervisor domains stopping','text':str(res)+' domains in hypervisor '+data['name']+' have been stopped.','icon':'success','type':'success'})
        socketio.emit('result',
                        info,
                        namespace='/sio_admins', 
                        room='hyper')

@socketio.on('hyperpool_edit', namespace='/sio_admins')
def socketio_hyperpool_edit(form_data):
    if current_user.role == 'admin': 
        data=app.isardapi.f.unflatten_dict(form_data)
        res=app.adminapi.update_table_dict('hypervisors_pools','default',{'viewer':{'domain':data['viewer']['domain']}})

        if res is True:
            info=json.dumps({'result':True,'title':'Edit hypervisor pool','text':'Hypervisor pool '+'default'+' has been edited.','icon':'success','type':'success'})
        else:
            info=json.dumps({'result':False,'title':'Edit hypervisor pool','text':'Hypervisor pool'+'default'+' can\'t be edited now.','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        info,
                        namespace='/sio_admins', 
                        room='hyper')
    else:
        info=json.dumps({'result':False,'title':'Hypervisor pool edit error','text':'Hypervisor pool should have at least one capability!','icon':'warning','type':'error'})        
        socketio.emit('result',
                        info,
                        namespace='/sio_admins', 
                        room='hyper') 
                        
'''
USERS
'''
@socketio.on('user_add', namespace='/sio_admins')
def socketio_user_add(form_data):
    if current_user.role == 'admin': 
        # ~ create_dict=app.isardapi.f.unflatten_dict(form_data)
        # ~ print(create_dict)
        res=app.adminapi.user_add(form_data)
        if res is True:
            data=json.dumps({'result':True,'title':'New user','text':'User '+form_data['name']+' has been created...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'New user','text':'User '+form_data['name']+' can\'t be created. Maybe it already exists!','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/sio_admins', 
                        room='users')

@socketio.on('user_edit', namespace='/sio_admins')
def socketio_user_edit(form_data):
    if current_user.role == 'admin': 
        res=app.adminapi.user_edit(form_data)
        if res is True:
            data=json.dumps({'result':True,'title':'User edit','text':'User '+form_data['name']+' has been updated...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'User edit','text':'User '+form_data['name']+' can\'t be updated!','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/sio_admins', 
                        room='users')

@socketio.on('user_passwd', namespace='/sio_admins')
def socketio_user_passwd(form_data):
    if current_user.role == 'admin': 
        res=app.adminapi.user_passwd(form_data)
        if res is True:
            data=json.dumps({'result':True,'title':'User edit','text':'User '+form_data['name']+' has been updated...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'User edit','text':'User '+form_data['name']+' can\'t be updated!','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/sio_admins', 
                        room='users')
                        
@socketio.on('user_delete', namespace='/sio_admins')
def socketio_user_delete(form_data):
    if current_user.role == 'admin': 
        # ~ create_dict=app.isardapi.f.unflatten_dict(form_data)
        # ~ print(create_dict)
        res=app.adminapi.user_delete(form_data)
        if res is True:
            data=json.dumps({'result':True,'title':'Delete user','text':'User '+form_data['name']+' has been created...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'New user','text':'User '+form_data['name']+' can\'t be created. Maybe it already exists!','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/sio_admins', 
                        room='users')    
                                            
@socketio.on('bulkusers_add', namespace='/sio_admins')
def socketio_bulkuser_add(form_data):
    if current_user.role == 'admin': 
        data=form_data['data']
        users=form_data['users']
        final_users=[{**u, **data} for u in users]
        res=app.adminapi.users_add(final_users)
        if res is True:
            data=json.dumps({'result':True,'title':'New user','text':'A total of '+str(len(final_users))+' users has been created...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'New user','text':'Something went wrong when creating '+str(len(final_users))+' can\'t be created. Maybe they already exists!','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/sio_admins', 
                        room='users')                    


@socketio.on('user_toggle', namespace='/sio_admins')
def socketio_user_toggle(data):
    if current_user.role == 'admin': 
        # ~ remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
        res=app.adminapi.user_toggle_active(data['pk'])
        if res is True:
            info=json.dumps({'result':True,'title':'User enable/disable','text':'User '+data['name']+' enable/disable success.','icon':'success','type':'success'})
        else:
            info=json.dumps({'result':False,'title':'User enable/disable','text':'User '+data['name']+' could not toggle enable status!','icon':'warning','type':'error'})        
        socketio.emit('result',
                        info,
                        namespace='/sio_admins', 
                        room='users')

@socketio.on('role_category_group_add', namespace='/sio_admins')
def socketio_role_category_group_add(form_data):
    if current_user.role == 'admin': 
        dict=app.isardapi.f.unflatten_dict(form_data)
        # ~ print(create_dict)
        res=app.adminapi.rcg_add(dict)
        if res is True:
            data=json.dumps({'result':True,'title':'New user','text':'User '+form_data['name']+' has been created...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'New user','text':'User '+form_data['name']+' can\'t be created. Maybe it already exists!','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/sio_admins', 
                        room='users')
                        
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
    None
    # ~ try:
        # ~ log.debug('USER: '+current_user.username+' DISCONNECTED')
    # ~ except:
        # ~ None

'''
DOMAINS
'''
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
        data=json.dumps({'result':False,'title':'New desktop','text':'Desktop '+create_dict['name']+' can\'t be created.','icon':'warning','type':'error'})
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
    create_dict['create_dict']['hardware']={**create_dict['hardware'], **create_dict['create_dict']['hardware']}
    create_dict.pop('hardware',None)

    if 'options' not in create_dict:
        create_dict['options']={'viewers':{'spice':{'fullscreen':False}}}
    else:
        if 'fullscreen' in create_dict['options']['viewers']['spice']:
            create_dict['options']['viewers']['spice']['fullscreen']=True
    
    res=app.isardapi.update_domain(create_dict.copy())
    if res is True:
        data=json.dumps({'id':create_dict['id'], 'result':True,'title':'Updated desktop','text':'Desktop '+create_dict['name']+' has been updated...','icon':'success','type':'success'})
    else:
        data=json.dumps({'id':create_dict['id'], 'result':True,'title':'Updated desktop','text':'Desktop '+create_dict['name']+' can\'t be updated.','icon':'warning','type':'error'})
    socketio.emit('edit_form_result',
                    data,
                    namespace='/sio_users', 
                    room='user_'+current_user.username)

@socketio.on('domain_template_add', namespace='/sio_users')
def socketio_domain_template_add(form_data):
    #~ Check if user has quota and rights to do it
    #~ if current_user.role=='admin':
        #~ None
        
    #~ if float(app.isardapi.get_user_quotas(current_user.username)['tqp']) >= 100:
        #~ flash('Quota for creating new templates is full','danger')
        #~ return redirect(url_for('desktops'))
    #~ # if app.isardapi.is_domain_id_unique
    #~ original=app.isardapi.get_domain(form_data['id'])

    partial_tmpl_dict=app.isardapi.f.unflatten_dict(form_data)
    partial_tmpl_dict=parseHardware(partial_tmpl_dict)
    partial_tmpl_dict['create_dict']['hardware']={**partial_tmpl_dict['hardware'], **partial_tmpl_dict['create_dict']['hardware']}
    partial_tmpl_dict.pop('hardware',None)
    from_id=partial_tmpl_dict['id']
    partial_tmpl_dict.pop('id',None)

    res=app.isardapi.new_tmpl_from_domain(from_id, partial_tmpl_dict, current_user.username)

    #~ create_dict=app.isardapi.f.unflatten_dict(form_data)
    #~ create_dict=parseHardware(create_dict)
    #~ res=app.isardapi.new_domain_from_tmpl(current_user.username, create_dict)

    if res is True:
        data=json.dumps({'result':True,'title':'New template','text':'Template '+partial_tmpl_dict['name']+' is being created...','icon':'success','type':'success'})
    else:
        data=json.dumps({'result':False,'title':'New template','text':'Template '+partial_tmpl_dict['name']+' can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    data,
                    namespace='/sio_users', 
                    room='user_'+current_user.username)

@socketio.on('domain_template_add', namespace='/sio_admins')
def socketio_admin_domain_template_add(form_data):
    #~ Check if user has quota and rights to do it
    #~ if current_user.role=='admin':
        #~ None
        
    #~ if float(app.isardapi.get_user_quotas(current_user.username)['tqp']) >= 100:
        #~ flash('Quota for creating new templates is full','danger')
        #~ return redirect(url_for('desktops'))
    #~ # if app.isardapi.is_domain_id_unique
    #~ original=app.isardapi.get_domain(form_data['id'])

    partial_tmpl_dict=app.isardapi.f.unflatten_dict(form_data)
    partial_tmpl_dict=parseHardware(partial_tmpl_dict)
    partial_tmpl_dict['create_dict']['hardware']={**partial_tmpl_dict['hardware'], **partial_tmpl_dict['create_dict']['hardware']}
    partial_tmpl_dict.pop('hardware',None)
    from_id=partial_tmpl_dict['id']
    partial_tmpl_dict.pop('id',None)

    res=app.isardapi.new_tmpl_from_domain(from_id, partial_tmpl_dict, current_user.username)

    #~ create_dict=app.isardapi.f.unflatten_dict(form_data)
    #~ create_dict=parseHardware(create_dict)
    #~ res=app.isardapi.new_domain_from_tmpl(current_user.username, create_dict)

    if res is True:
        data=json.dumps({'result':True,'title':'New template','text':'Template '+partial_tmpl_dict['name']+' is being created...','icon':'success','type':'success'})
    else:
        data=json.dumps({'result':False,'title':'New template','text':'Template '+partial_tmpl_dict['name']+' can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    data,
                    namespace='/sio_admins', 
                    room='domains')
                                        
@socketio.on('domain_update', namespace='/sio_users')
def socketio_domains_update(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    socketio.emit('result',
                    app.isardapi.update_table_status(current_user.username, 'domains', data,remote_addr),
                    namespace='/sio_users', 
                    room='user_'+current_user.username)

@socketio.on('domain_update', namespace='/sio_admins')
def socketio_admin_domains_update(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    socketio.emit('result',
                    app.isardapi.update_table_status(current_user.username, 'domains', data,remote_addr),
                    namespace='/sio_admins', 
                    room='domains')
                    
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


# ~ {'create_dict': {'hardware': {'boot_order': ['iso'],
                              # ~ 'graphics': ['vnc'],
                              # ~ 'interfaces': ['eli-c1j-bridge'],
                              # ~ 'memory': 11008000,
                              # ~ 'vcpus': '4',
                              # ~ 'videos': ['qxl32']}},
 # ~ 'forced_hyp': 'vdesktop1',
 # ~ 'hypervisors_pools': ['admin_test_pool'],
 # ~ 'ids': ['_cor47987476_Programas',
         # ~ '_valejandre_programas',
         # ~ '_jfuentes_Plantilla_de_Mia',
         # ~ '_coc39947402_PIEDRA',
         # ~ '_mjmartinez_Pepa',
         # ~ '_cor26069823_PC-2',
         # ~ '_opuigdomenech_PC_BASIC',
         # ~ '_cor47576923_nueva_pr',
         # ~ '_mcapdevila_M2-W7',
         # ~ '_cor43636725_M0002',
         # ~ '_lespinos_Lluis_ITEC',
         # ~ '_lespinos_LLUIS',
         # ~ '_cor47952154_EDRI',
         # ~ '_coc43573404_Dgc8',
         # ~ '_coc46746373_AUTOCAD_v2',
         # ~ '_acontreras_aaaaa']}



@socketio.on('domain_bulkedit', namespace='/sio_admins')
def socketio_admins_domain_bulkedit(form_data):
    #~ Check if user has quota and rights to do it
    #~ if current_user.role=='admin':
        #~ None
    create_dict=app.isardapi.f.unflatten_dict(form_data)
    create_dict=parseHardware(create_dict)
    create_dict['create_dict']={'hardware':create_dict['hardware'].copy()}
    create_dict.pop('hardware',None)
    # ~ import pprint
    # ~ pprint.pprint(create_dict)
    res=app.adminapi.domains_update(create_dict.copy())
    if res is True:
        data=json.dumps({'id':create_dict['ids'], 'result':True,'title':'Updated desktops','text':'Desktop '+str(create_dict['ids'])+' has been updated...','icon':'success','type':'success'})
    else:
        data=json.dumps({'id':create_dict['ids'], 'result':False,'title':'Updated desktops','text':'Desktop '+str(create_dict['ids'])+' can\'t be updated.','icon':'warning','type':'error'})
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
    
@socketio.on('domain_viewer', namespace='/sio_users')
def socketio_domains_viewer(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    viewer_data=isardviewer.get_viewer(data,current_user,remote_addr)
    if viewer_data:
        socketio.emit('domain_viewer',
                        json.dumps(viewer_data),
                        namespace='/sio_users', 
                        room='user_'+current_user.username)          
        
    else:
        msg=json.dumps({'result':True,'title':'Viewer','text':'Viewer could not be opened. Try again.','icon':'warning','type':'error'})
        socketio.emit('result',
                        msg,
                        namespace='/sio_users', 
                        room='user_'+current_user.username)     

@socketio.on('domain_viewer', namespace='/sio_admins')
def socketio_admin_domains_viewer(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    viewer_data=isardviewer.get_viewer(data,current_user,remote_addr)
    if viewer_data:
        socketio.emit('domain_viewer',
                        json.dumps(viewer_data),
                        namespace='/sio_admins', 
                        room='user_'+current_user.username)          
        
    else:
        msg=json.dumps({'result':True,'title':'Viewer','text':'Viewer could not be opened. Try again.','icon':'warning','type':'error'})
        socketio.emit('result',
                        msg,
                        namespace='/sio_users', 
                        room='user_'+current_user.username)   

@socketio.on('disposable_viewer', namespace='/sio_disposables')
def socketio_disposables_viewer(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    viewer_data=isardviewer.get_viewer(data,current_user,remote_addr)
    if viewer_data:
        socketio.emit('disposable_viewer',
                        json.dumps(viewer_data),
                        namespace='/sio_disposables', 
                        room='disposable_'+remote_addr)           
        
    else:
        msg=json.dumps({'result':True,'title':'Viewer','text':'Viewer could not be opened. Try again.','icon':'warning','type':'error'})
        socketio.emit('result',
                        msg,
                        namespace='/sio_disposables', 
                        room='disposable_'+remote_addr)      
    
    
    
    
    
    
    
    
    
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    if data['pk'].startswith('_disposable_'+remote_addr.replace('.','_')+'_'):
        send_viewer(data,kind='disposable',remote_addr=remote_addr)
    else:
        msg=json.dumps({'result':True,'title':'Viewer','text':'Viewer could not be opened. Try again.','icon':'warning','type':'error'})
        socketio.emit('result',
                        msg,
                        namespace='/sio_disposables', 
                        room='disposable_'+remote_addr) 
                        
#~ def send_viewer(data,kind='domain',remote_addr): 
    #~ if data['kind'] == 'file':
        #~ consola=app.isardviewer.get_viewer_ticket(data['pk'],remote_addr=remote_addr)
        #~ if kind=='domain':
            #~ socketio.emit('domain_viewer',
                            #~ json.dumps({'kind':data['kind'],'ext':consola[0],'mime':consola[1],'content':consola[2]}),
                            #~ namespace='/sio_users', 
                            #~ room='user_'+current_user.username)  
        #~ else:
            #~ socketio.emit('disposable_viewer',
                            #~ json.dumps({'kind':data['kind'],'ext':consola[0],'mime':consola[1],'content':consola[2]}),
                            #~ namespace='/sio_disposables', 
                            #~ room='disposable_'+remote_addr)              
        #~ # ~ return Response(consola, 
                        #~ # ~ mimetype="application/x-virt-viewer",
                        #~ # ~ headers={"Content-Disposition":"attachment;filename=consola.vv"})
    #~ else:
        #~ if data['kind'] == 'xpi':
            #~ viewer=app.isardapi.get_spice_xpi(data['pk'])  #,remote_addr=remote_addr)

        #~ if data['kind'] == 'html5':
            #~ viewer=app.isardapi.get_domain_spice(data['pk'],remote_addr=remote_addr)
            #~ ##### Change this when engine opens ports accordingly (without tls)
        #~ if viewer is not False:
            #~ if viewer['port']:
                #~ viewer['port'] = viewer['port'] if viewer['port'] else viewer['tlsport']
                #~ viewer['port'] = "5"+ viewer['port']
                #viewer['port']=viewer['port']-1
            #~ if kind=='domain':
                #~ socketio.emit('domain_viewer',
                                #~ json.dumps({'kind':data['kind'],'viewer':viewer}),
                                #~ namespace='/sio_users', 
                                #~ room='user_'+current_user.username)
            #~ else:
                #~ socketio.emit('disposable_viewer',
                                #~ json.dumps({'kind':data['kind'],'viewer':viewer}),
                                #~ namespace='/sio_disposables', 
                                #~ room='disposable_'+remote_addr)                 
        #~ else:
            #~ msg=json.dumps({'result':True,'title':'Viewer','text':'Viewer could not be opened. Try again.','icon':'warning','type':'error'})
            #~ if kind=='domain':
                #~ socketio.emit('result',
                                #~ msg,
                                #~ namespace='/sio_users', 
                                #~ room='user_'+current_user.username)
            #~ else:
                #~ socketio.emit('result',
                                #~ msg,
                                #~ namespace='/sio_disposables', 
                                #~ room='disposable_'+remote_addr) 
                                                            
'''
MEDIA
'''
@socketio.on('media_update', namespace='/sio_admins')
def socketio_admin_media_update(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    socketio.emit('result',
                    app.isardapi.update_table_status(current_user.username, 'media', data,remote_addr),
                    namespace='/sio_admins', 
                    room='media')
                    
    
@socketio.on('media_update', namespace='/sio_users')
def socketio_media_update(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    socketio.emit('result',
                    app.isardapi.update_table_status(current_user.username, 'media', data,remote_addr),
                    namespace='/sio_users', 
                    room='user_'+current_user.username)  
       

@socketio.on('media_add', namespace='/sio_admins')
def socketio_admin_media_add(form_data):
    form_data['hypervisors_pools']=[form_data['hypervisors_pools']]
    res=app.adminapi.media_add(current_user.username, form_data)
    if res is True:
        info=json.dumps({'result':True,'title':'New media','text':'Media is being downloaded...','icon':'success','type':'success'})
    else:
        info=json.dumps({'result':False,'title':'New media','text':'Media can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    info,
                    namespace='/sio_admins', 
                    room='media')

@socketio.on('media_add', namespace='/sio_users')
def socketio_media_add(form_data):
    form_data['hypervisors_pools']=[form_data['hypervisors_pools']]
    res=app.adminapi.media_add(current_user.username, form_data)
    if res is True:
        info=json.dumps({'result':True,'title':'New media','text':'Media is being downloaded...','icon':'success','type':'success'})
    else:
        info=json.dumps({'result':False,'title':'New media','text':'Media can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    info,
                    namespace='/sio_users', 
                    room='user_'+current_user.username)


@socketio.on('domain_media_add', namespace='/sio_admins')
def socketio_admin_domains_media_add(form_data):
    create_dict=app.isardapi.f.unflatten_dict(form_data)
    create_dict['hardware']['boot_order']=[create_dict['hardware']['boot_order']]
    create_dict['hardware']['graphics']=[create_dict['hardware']['graphics']]
    create_dict['hardware']['videos']=[create_dict['hardware']['videos']]
    create_dict['hardware']['interfaces']=[create_dict['hardware']['interfaces']]
    create_dict['hardware']['memory']=int(create_dict['hardware']['memory'])*1024
    create_dict['hardware']['vcpus']=create_dict['hardware']['vcpus']
    create_dict['create_from_virt_install_xml']= create_dict['install']
    create_dict.pop('install',None)
    disk_size=create_dict['disk_size']+'G'
    create_dict.pop('disk_size',None)
    name=create_dict['name']
    create_dict.pop('name',None)
    description=create_dict['description']
    create_dict.pop('description',None)
    hyper_pools=[create_dict['hypervisors_pools']]
    create_dict.pop('hypervisors_pools',None)
    # ~ icon=create_dict['icon']
    icon='circle-o'
    create_dict.pop('icon',None)
    create_dict.pop('allowed',None)
    res=app.adminapi.domain_from_media(current_user.username, name, description, icon, create_dict, hyper_pools, disk_size)
    if res is True:
        info=json.dumps({'result':True,'title':'New desktop','text':'Desktop '+name+' is being created...','icon':'success','type':'success'})
    else:
        info=json.dumps({'result':False,'title':'New desktop','text':'Desktop '+name+' can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    info,
                    namespace='/sio_admins', 
                    room='user_'+current_user.username)

@socketio.on('domain_media_add', namespace='/sio_users')
def socketio_domains_media_add(form_data):
    log.info(form_data)
    create_dict=app.isardapi.f.unflatten_dict(form_data)
    create_dict['hardware']['boot_order']=[create_dict['hardware']['boot_order']]
    create_dict['hardware']['graphics']=[create_dict['hardware']['graphics']]
    create_dict['hardware']['videos']=[create_dict['hardware']['videos']]
    create_dict['hardware']['interfaces']=[create_dict['hardware']['interfaces']]
    create_dict['hardware']['memory']=int(create_dict['hardware']['memory'])*1024
    create_dict['hardware']['vcpus']=create_dict['hardware']['vcpus']
    create_dict['create_from_virt_install_xml']= create_dict['install']
    create_dict.pop('install',None)
    disk_size=create_dict['disk_size']+'G'
    create_dict.pop('disk_size',None)
    name=create_dict['name']
    create_dict.pop('name',None)
    description=create_dict['description']
    create_dict.pop('description',None)
    hyper_pools=[create_dict['hypervisors_pools']]
    create_dict.pop('hypervisors_pools',None)
    # ~ icon=create_dict['icon']
    icon='circle-o'
    create_dict.pop('icon',None)
    create_dict.pop('allowed',None)
    res=app.adminapi.domain_from_media(current_user.username, name, description, icon, create_dict, hyper_pools, disk_size)
    if res is True:
        info=json.dumps({'result':True,'title':'New desktop','text':'Desktop '+name+' is being created...','icon':'success','type':'success'})
    else:
        info=json.dumps({'result':False,'title':'New desktop','text':'Desktop '+name+' can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    info,
                    namespace='/sio_users', 
                    room='user_'+current_user.username)
                    
## Disposables
@socketio.on('connect', namespace='/sio_disposables')
def socketio_disposables_connect():
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    if app.isardapi.show_disposable(remote_addr):
        join_room('disposable_'+remote_addr)


                                    
@socketio.on('disposables_add', namespace='/sio_disposables')
def socketio_disposables_add(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    template=data['pk'] ##request.get_json(force=True)['pk']
    ## Checking permissions
    disposables = app.isardapi.show_disposable(remote_addr)
    # ~ print([d['id'] for d in disposables['disposables'] if d['id']==template])
    if disposables and len([d['id'] for d in disposables['disposables'] if d['id']==template]):
        id=app.isardapi.new_domain_disposable_from_tmpl(remote_addr,template)
    else:
        id=False
    if id:
        data=json.dumps({'result':True,'title':'New disposable','text':'Disposable '+id+' for your client is being created. Please wait...','icon':'success','type':'success'})
    else:
        data=json.dumps({'result':True,'title':'New disposable','text':'Disposable for your can\'t be created. Please try again.','icon':'warning','type':'error'})
    socketio.emit('result',
                    data,
                    namespace='/sio_disposables', 
                    room='disposable_'+remote_addr)



## Alloweds
@socketio.on('allowed_update', namespace='/sio_admins')
def socketio_admin_allowed_update(data):
    if current_user.role == 'admin': 
        res = app.adminapi.update_table_dict(data['table'], data['id'],{'allowed':data['allowed']})
        if res:
            data=json.dumps({'result':True,'title':'Update permissions','text':'Permissions updated for '+data['id'],'icon':'success','type':'success'})
        else:
            data=json.dumps({'result':True,'title':'Update permissions','text':'Something went wrong. Could not update permissions!','icon':'warning','type':'error'})
        socketio.emit('allowed_result',
                        data,
                        namespace='/sio_admins', 
                        room='user_'+current_user.username)

@socketio.on('allowed_update', namespace='/sio_users')
def socketio_allowed_update(data):
    res = app.adminapi.update_table_dict(data['table'], data['id'],{'allowed':data['allowed']})
    if res:
        info=json.dumps({'result':data,'title':'Update permissions','text':'Permissions updated for '+data['id'],'icon':'success','type':'success'})
    else:
        info=json.dumps({'result':False,'title':'Update permissions','text':'Something went wrong. Could not update permissions!','icon':'warning','type':'error'})
    socketio.emit('allowed_result',
                    info,
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
def socketio_admins_joinrooms(join_rooms):
    if current_user.role=='admin':
        for rm in join_rooms:
            join_room(rm)
            # ~ log.debug('USER: '+current_user.username+' JOINED ROOM: '+rm)

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
    res=app.adminapi.domain_from_virtbuilder(current_user.username, name, description, icon, create_dict, hyper_pools, disk_size)
    if res is True:
        info=json.dumps({'result':True,'title':'New desktop','text':'Desktop '+name+' is being created...','icon':'success','type':'success'})
    else:
        info=json.dumps({'result':False,'title':'New desktop','text':'Desktop '+name+' can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    info,
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
        data=json.dumps({'result':False,'title':'New scheduler','text':'Scheduler can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    data,
                    namespace='/sio_admins', 
                    room='config')

                    
@socketio.on('disconnect', namespace='/sio_admins')
def socketio_admins_disconnect():
    leave_room('admins')
    try:
        leave_room('user_'+current_user.username)
    except Exception as e:
        log.debug('USER leaved without disconnect')
    #~ log.debug('USER: '+current_user.username+' DISCONNECTED')
    

