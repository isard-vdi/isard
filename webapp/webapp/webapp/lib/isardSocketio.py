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
import traceback

from ..lib.log import *

import rethinkdb as r
from rethinkdb.errors import ReqlDriverError
from ..lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

#~ from .decorators import ownsid
from webapp import app

from .isardViewer import isardViewer
isardviewer = isardViewer()


from ..lib.quotas import QuotaLimits
quotas = QuotaLimits()

socketio = SocketIO(app)
threads = {}

## Domains Threading
class DomainsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in r.table('domains').without('xml','history_domain').changes(include_initial=False).run(db.conn):
                        #~ .pluck('id','kind','hyp_started','name','description','icon','status','user')
                        if self.stop==True: break
                        if c['new_val'] == None:
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
                                try:
                                    # New threaded events in ds.py toggles status before it can be processed here.
                                    data['derivates']=app.adminapi.get_admin_domains_with_derivates(id=c['new_val']['id'],kind='template')
                                    data['kind']=app.isardapi.get_template_kind(data['user'],data)
                                except:
                                    continue
                                    
                        socketio.emit(event, 
                                        json.dumps(data), 
                                        #~ json.dumps(app.isardapi.f.flatten_dict(data)), 
                                        namespace='/isard-admin/sio_users', 
                                        room='user_'+data['user'])
                        socketio.emit('user_quota', 
                                        json.dumps(quotas.get(data['user'])), 
                                        namespace='/isard-admin/sio_users', 
                                        room='user_'+data['user'])
                        socketio.emit('user_quota', 
                                        json.dumps(quotas.get(data['user'])), 
                                        namespace='/isard-admin/sio_admins', 
                                        room='user_'+data['user'])  
                        socketio.emit('user_quota', 
                                        json.dumps(quotas.get(False,admin=True)), 
                                        namespace='/isard-admin/sio_admins', 
                                        room='domains')                                                                          
                        """ socketio.emit('user_quota', 
                                        json.dumps(quotas.get('local-default-admin-admin')), 
                                        namespace='/isard-admin/sio_admins', 
                                        room='domains') """
                        ## Admins should receive all updates on /isard-admin/admin namespace
                        socketio.emit(event, 
                                        json.dumps(data),
                                        #~ json.dumps(app.isardapi.f.flatten_dict(data)), 
                                        namespace='/isard-admin/sio_admins', 
                                        room=data['category']+'_domains')  
                        socketio.emit(event, 
                                        json.dumps(data),
                                        #~ json.dumps(app.isardapi.f.flatten_dict(data)), 
                                        namespace='/isard-admin/sio_admins', 
                                        room='domains')
            except ReqlDriverError:
                print('DomainsThread: Rethink db connection lost!')
                log.error('DomainsThread: Rethink db connection lost!')
                time.sleep(.5)
            except Exception as e:
                print('DomainsThread internal error: \n'+traceback.format_exc())
                log.error('DomainsThread internal error: \n'+traceback.format_exc())
               
        print('DomainsThread ENDED!!!!!!!')
        log.error('DomainsThread ENDED!!!!!!!')      

def start_domains_thread():
    global threads
    if 'domains' not in threads: threads['domains']=None
    if threads['domains'] == None:
        threads['domains'] = DomainsThread()
        threads['domains'].daemon = True
        threads['domains'].start()
        log.info('DomainsThread Started')

            
## Domains Stats Threading
################ NOT USED
class DomainsStatsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False
        self.domains= dict()

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in r.table('domains_status').pluck('name','when','status').merge({'table':'stats'}).changes(include_initial=False).union(
                            r.table('domains').get_all(r.args(['Started','Stopping','Stopped']),index='status').pluck('id','name','os','hyp_started','status').merge({"table": "domains"}).changes(include_initial=False)).run(db.conn):
                        if self.stop==True: break

                        if c['new_val'] != None:
                            if not c['new_val']['name'].startswith('_'): continue
                            if c['new_val']['name'] not in self.domains.keys():
                                if r.table('domains').get(c['new_val']['name']).run(db.conn) == None: continue
                                domain=r.table('domains').get(c['new_val']['name']).pluck('id','name','status','hyp_started','os').run(db.conn)
                                self.domains[c['new_val']['name']]=domain
                            else:
                                domain=self.domains[c['new_val']['name']]
                            if domain != None: #This if can be removed when vimet is shutdown
                                    new_dom=domain.copy()
                                    if domain['status']=='Started':
                                        new_dom['status']=c['new_val']['status']
                                        socketio.emit('desktop_status', 
                                                        json.dumps(new_dom), 
                                                        namespace='/isard-admin/sio_users', 
                                                        room='user_'+c['new_val']['name'].split('_')[1])
                                        socketio.emit('desktop_status', 
                                                        json.dumps(new_dom), 
                                                        namespace='/isard-admin/sio_admins', 
                                                        room='domains_status')

                                    else:
                                        self.domains.pop(c['new_val']['name'],None)
                                        socketio.emit('desktop_stopped', 
                                                        json.dumps(new_dom), 
                                                        namespace='/isard-admin/sio_admins', 
                                                        room='domains_status')                                                   
                                    new_dom=None


            except ReqlDriverError:
                print('DomainsStatsThread: Rethink db connection lost!')
                log.error('DomainsStatsThread: Rethink db connection lost!')
                time.sleep(1)
            except Exception as e:
                print('DomainsStatsThread internal error: \n'+traceback.format_exc())
                log.error('DomainsStatsThread internal error: \n'+traceback.format_exc())
               
        print('DomainsStatsThread ENDED!!!!!!!')
        log.error('DomainsStatsThread ENDED!!!!!!!')     


def start_domains_stats_thread():
    global threads

    if 'domains_stats' not in threads: threads['domains_stats']=None
    if threads['domains_stats'] == None:
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
        while True:
            try:
                with app.app_context():
                    for c in r.table('domains').get_all(r.args(['Downloaded', 'DownloadFailed','DownloadStarting', 'Downloading', 'DownloadAborting','ResetDownloading']),index='status').pluck('id','name','description','icon','progress','status','user','category').merge({'table':'domains'}).changes(include_initial=False).union(
                            r.table('media').get_all(r.args(['Deleting', 'Deleted', 'Downloaded', 'DownloadFailed', 'DownloadStarting', 'Downloading', 'Download', 'DownloadAborting','ResetDownloading']),index='status').merge({'table':'media'}).changes(include_initial=False)).run(db.conn):
                        if self.stop==True: break
                        if c['new_val'] == None:
                            data=c['old_val']
                            event=c['old_val']['table']+'_delete'
                        else:
                            data=c['new_val']
                            event=c['new_val']['table']+'_data'
                        ## Admins should receive all updates on /isard-admin/admin namespace
                        ## Users should receive not only their media updates, also the shared one's with them!
                        socketio.emit(event, 
                                        json.dumps(data), 
                                        namespace='/isard-admin/sio_users', 
                                        room='user_'+data['user'])
                        socketio.emit('user_quota', 
                                        json.dumps(quotas.get(data['user'])), 
                                        namespace='/isard-admin/sio_users', 
                                        room='user_'+data['user'])
                        socketio.emit('user_quota', 
                                        json.dumps(quotas.get(data['user'])), 
                                        namespace='/isard-admin/sio_admins', 
                                        room='user_'+data['user']) 
                        socketio.emit('user_quota', 
                                        json.dumps(quotas.get(False,admin=True)), 
                                        namespace='/isard-admin/sio_admins', 
                                        room='media')                                                                           
                        """ socketio.emit('user_quota', 
                                        json.dumps(quotas.get('local-default-admin-admin')), 
                                        namespace='/isard-admin/sio_admins', 
                                        room='media') """  
                        if data['user'] != "admin":
                            socketio.emit(event, 
                                            json.dumps(data),
                                            #~ json.dumps(app.isardapi.f.flatten_dict(data)), 
                                            namespace='/isard-admin/sio_admins', 
                                            room=data['category']+'_domains')                                                     
                        socketio.emit(event, 
                                        json.dumps(data),
                                        #~ json.dumps(app.isardapi.f.flatten_dict(data)), 
                                        namespace='/isard-admin/sio_admins', 
                                        room=data['category']+'_media')  
                        socketio.emit(event, 
                                        json.dumps(data),
                                        namespace='/isard-admin/sio_admins', 
                                        room='media')
            except ReqlDriverError:
                print('MediaThread: Rethink db connection lost!')
                log.error('MediaThread: Rethink db connection lost!')
                time.sleep(5)
            except Exception as e:
                print('MediaThread internal error: \n'+traceback.format_exc())
                log.error('MediaThread internal error: \n'+traceback.format_exc())
               
        print('MediaThread ENDED!!!!!!!')
        log.error('MediaThread ENDED!!!!!!!') 

def start_media_thread():
    global threads
    if 'media' not in threads: threads['media']=None
    if threads['media'] == None:
        threads['media'] = MediaThread()
        threads['media'].daemon = True
        threads['media'].start()
        log.info('MediaThread Started')



## RESOURCES Threading
class ResourcesThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in r.table('graphics').merge({'table':'graphics'}).changes(include_initial=False).union(
                            r.table('videos').merge({'table':'videos'}).changes(include_initial=False).union(
                            r.table('interfaces').merge({'table':'interfaces'}).changes(include_initial=False).union(
                            r.table('qos_net').merge({'table':'qos_net'}).changes(include_initial=False).union(
                            r.table('qos_disk').merge({'table':'qos_disk'}).changes(include_initial=False).union(
                            r.table('boots').merge({'table':'boots'}).changes(include_initial=False)))))).run(db.conn):
                        if self.stop==True: break
                        if c['new_val'] == None:
                            data={'table':c['old_val']['table'],'data':c['old_val']}
                            event='delete'
                        else:
                            data={'table':c['new_val']['table'],'data':c['new_val']}
                            event='data'
                        ## Admins should receive all updates on /isard-admin/admin namespace                  
                        socketio.emit(event, 
                                        json.dumps(data), #app.isardapi.f.flatten_dict(data)), 
                                        namespace='/isard-admin/sio_admins', 
                                        room='resources')                                  
            except ReqlDriverError:
                print('ResourcesThread: Rethink db connection lost!')
                log.error('ResourcesThread: Rethink db connection lost!')
                time.sleep(6)
            except Exception as e:
                print('ResourcesThread internal error: \n'+traceback.format_exc())
                log.error('ResourcesThread internal error: \n'+traceback.format_exc())

def start_resources_thread():
    global threads
    if 'resources' not in threads: threads['resources']=None
    if threads['resources'] == None:
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
        while True:
            try:
                with app.app_context():
                    for c in r.table('users').merge({'table':'users'}).changes(include_initial=False).union(
                        r.table('categories').merge({'table':'categories'}).changes(include_initial=False).union(
                            r.table('groups').merge({'table':'groups'}).changes(include_initial=False))).run(db.conn):
                        if self.stop==True: break
                        if c['new_val'] == None:
                            data=c['old_val']
                            table=c['old_val']['table']
                            event=table+'_delete'
                        else:
                            data=c['new_val']
                            table=c['new_val']['table']
                            event=table+'_data'
                        

                            ## Send de event to de already removed user?
                            ## This should only be done if we kick outuser on socketio event
                            ##socketio.emit(event, 
                            ##                json.dumps(app.isardapi.f.flatten_dict(data)), 
                            ##                namespace='/isard-admin/sio_users', 
                            ##                room='user_'+data['id'])

                        ## Quotas only when user is not deleted
                        ##if event != 'user_delete' and table == 'users':
                            #socketio.emit('user_quota', 
                            #                json.dumps(quotas.get(data['id'])), 
                            #                namespace='/isard-admin/sio_users', 
                            #                room='user_'+data['id'])
                            #socketio.emit('user_quota', 
                            #                json.dumps(quotas.get(data['id'])), 
                            #                namespace='/isard-admin/sio_admins', 
                            #                room='user_'+data['id'])   

                        ## Managers updates
                        if table == 'users':
                            category=data['category']
                        elif table == 'categories':
                            category=data['id']
                        else:
                            category=data['parent_category'] if 'parent_category' in data.keys() else False 
                        
                        if category != False:
                            socketio.emit(event, 
                                            json.dumps(data),
                                            #~ json.dumps(app.isardapi.f.flatten_dict(data)), 
                                            namespace='/isard-admin/sio_admins', 
                                            room=category+'_users') 
                        if table == "users":
                            # Update user updated room
                            socketio.emit('user_quota', 
                                            json.dumps(quotas.get(data['id'])), 
                                            namespace='/isard-admin/sio_users', 
                                            room='user_'+data['id'])
                            # Managers can update tables so need quota updates on sio_admins
                            socketio.emit('user_quota', 
                                            json.dumps(quotas.get(data['id'])), 
                                            namespace='/isard-admin/sio_admins', 
                                            room='user_'+data['id'])  
                        else:
                            ## Managers need update on its own category/group changes
                            if table != 'categories':
                                socketio.emit('user_quota', 
                                                json.dumps(quotas.get(False,category_id=category)), 
                                                namespace='/isard-admin/sio_admins', 
                                                room=category+'_users')  

                        ## Admins should receive all updates on /isard-admin/admin namespace
                        socketio.emit('user_quota', 
                                        json.dumps(quotas.get(False,admin=True)), 
                                        namespace='/isard-admin/sio_admins', 
                                        room='users')
                                    
                        #json.dumps(app.isardapi.f.flatten_dict(data)),
                        socketio.emit(event, 
                                        json.dumps(data),
                                        namespace='/isard-admin/sio_admins', 
                                        room='users')
            except ReqlDriverError:
                print('UsersThread: Rethink db connection lost!')
                log.error('UsersThread: Rethink db connection lost!')
                time.sleep(2)
            except Exception as e:
                print('UsersThread internal error: \n'+traceback.format_exc())
                log.error('UsersThread internal error: \n'+traceback.format_exc())

def start_users_thread():
    global threads
    if 'users' not in threads: threads['users']=None
    if threads['users'] == None:
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
        while True:
            try:
                with app.app_context():
                    for c in r.table('hypervisors').merge({"table": "hyper"}).changes(include_initial=False).union(
                                r.table('hypervisors_status').pluck('hyp_id','domains',{'cpu_percent':{'used'}},{'load':{'percent_free'}}).merge({"table": "hyper_status"}).changes(include_initial=False)).run(db.conn):
                                #~ .union(
                                #~ r.table('domains').get_all(r.args(['Started','Stopping','Stopped']),index='status').pluck('id','name','hyp_started','status').merge({"table": "domains"}).changes(include_initial=False)).run(db.conn):
                        if self.stop==True: break
                        if c['new_val'] == None:
                            if c['old_val']['table']=='hyper':
                                socketio.emit('hyper_deleted', 
                                                json.dumps(c['old_val']['id']), 
                                                namespace='/isard-admin/sio_admins', 
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
                                            namespace='/isard-admin/sio_admins', 
                                            room='hyper')  
            except ReqlDriverError:
                print('HypervisorsThread: Rethink db connection lost!')
                log.error('HypervisorsThread: Rethink db connection lost!')
                time.sleep(2)
            except Exception as e:
                print('HypervisorsThread internal error: \n'+traceback.format_exc())
                log.error('HypervisorsThread internal error: \n'+traceback.format_exc())
                    
def start_hypervisors_thread():
    global threads
    if 'hypervisors' not in threads: threads['hypervisors']=None
    if threads['hypervisors'] == None:
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
        while True:
            try:
                with app.app_context():
                    for c in r.table('backups').merge({'table':'backups'}).changes(include_initial=False).union(
                        r.table('scheduler_jobs').has_fields('name').without('job_state').merge({'table':'scheduler_jobs'}).changes(include_initial=False)).run(db.conn):
                        if self.stop==True: break
                        if c['new_val'] == None:
                            event= '_deleted'
                            socketio.emit(c['old_val']['table']+event, 
                                            json.dumps(c['old_val']), 
                                            namespace='/isard-admin/sio_admins', 
                                            room='config')
                        else:
                            event= '_data'
                            socketio.emit(c['new_val']['table']+event, 
                                            json.dumps(c['new_val']),
                                            namespace='/isard-admin/sio_admins', 
                                            room='config') 
                                                                    
                            #~ event= 'backup_deleted' if c['old_val']['table']=='backups' else 'sch_deleted'
                            #~ socketio.emit(event, 
                                            #~ json.dumps(c['old_val']), 
                                            #~ namespace='/isard-admin/sio_admins', 
                                            #~ room='config')
                        #~ else:
                            #~ event='backup_data' if c['new_val']['table']=='backups' else 'sch_data'
                            #~ if event=='sch_data' and 'name' not in c['new_val'].keys():
                                #~ continue
                            #~ socketio.emit(event, 
                                            #~ json.dumps(c['new_val']),
                                            #~ namespace='/isard-admin/sio_admins', 
                                            #~ room='config') 
            except ReqlDriverError:
                print('ConfigThread: Rethink db connection lost!')
                log.error('ConfigThread: Rethink db connection lost!')
                time.sleep(15)
            except Exception as e:
                print('ConfigThread internal error: \n'+traceback.format_exc())
                log.error('ConfigThread internal error: \n'+traceback.format_exc())
                    
def start_config_thread():
    global threads
    if 'config' not in threads: threads['config']=None
    if threads['config'] == None:
        threads['config'] = ConfigThread()
        threads['config'].daemon = True
        threads['config'].start()
        log.info('ConfigThread Started')


## Hypervisors namespace

@socketio.on('hyper_add', namespace='/isard-admin/sio_admins')
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
            # ~ create_dict['viewer']={'proxy_hyper_host':create_dict.pop('proxy_hyper_host'),
                                    # ~ 'proxy_video':create_dict.pop('proxy_video'),
                                    # ~ 'static':create_dict.pop('static')}            
            res=app.adminapi.hypervisor_add(create_dict)

            if res is True:
                info=json.dumps({'result':True,'title':'New hypervisor','text':'Hypervisor '+create_dict['hostname']+' has been created.','icon':'success','type':'success'})
                ### Engine restart needed
                
                ### Warning
            else:
                info=json.dumps({'result':False,'title':'New hypervisor','text':'Hypervisor '+create_dict['hostname']+' can\'t be created. Maybe it already exists!','icon':'warning','type':'error'})
            socketio.emit('add_form_result',
                            info,
                            namespace='/isard-admin/sio_admins', 
                            room='hyper')
        else:
            info=json.dumps({'result':False,'title':'Hypervisor add error','text':'Hypervisor should have at least one capability!','icon':'warning','type':'error'})        
            socketio.emit('result',
                            info,
                            namespace='/isard-admin/sio_admins', 
                            room='hyper')            

@socketio.on('hyper_edit', namespace='/isard-admin/sio_admins')
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
            # ~ create_dict['viewer']={'proxy_hyper_host':create_dict.pop('proxy_hyper_host'),
                                    # ~ 'proxy_video':create_dict.pop('proxy_video'),
                                    # ~ 'static':create_dict.pop('static')}
            
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
                            namespace='/isard-admin/sio_admins', 
                            room='hyper')
        else:
            info=json.dumps({'result':False,'title':'Hypervisor edit error','text':'Hypervisor should have at least one capability!','icon':'warning','type':'error'})        
            socketio.emit('result',
                            info,
                            namespace='/isard-admin/sio_admins', 
                            room='hyper') 

@socketio.on('hyper_delete', namespace='/isard-admin/sio_admins')
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
                        namespace='/isard-admin/sio_admins', 
                        room='hyper')

@socketio.on('hyper_toggle', namespace='/isard-admin/sio_admins')
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
                        namespace='/isard-admin/sio_admins', 
                        room='hyper')

@socketio.on('hyper_domains_stop', namespace='/isard-admin/sio_admins')
def socketio_hyper_domains_stop(data):
    if current_user.role == 'admin': 
        # ~ remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
        res=app.adminapi.domains_stop(hyp_id=data['pk'],without_viewer=data['without_viewer'])
        if res == False:
            info=json.dumps({'result':False,'title':'Hypervisor domains stoping','text':'Domains in '+data['name']+' hypervisor could not be stopped now.!','icon':'warning','type':'error'}) 
            
        else:
            info=json.dumps({'result':True,'title':'Hypervisor domains stopping','text':str(res)+' domains in hypervisor '+data['name']+' have been stopped.','icon':'success','type':'success'})
        socketio.emit('result',
                        info,
                        namespace='/isard-admin/sio_admins', 
                        room='hyper')

@socketio.on('hyperpool_edit', namespace='/isard-admin/sio_admins')
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
                        namespace='/isard-admin/sio_admins', 
                        room='hyper')
    else:
        info=json.dumps({'result':False,'title':'Hypervisor pool edit error','text':'Hypervisor pool should have at least one capability!','icon':'warning','type':'error'})        
        socketio.emit('result',
                        info,
                        namespace='/isard-admin/sio_admins', 
                        room='hyper') 
                        
'''
USERS
'''
@socketio.on('user_add', namespace='/isard-admin/sio_admins')
def socketio_user_add(form_data):
    if current_user.role == 'admin' or current_user.role == 'manager': 
        exceeded = quotas.check('NewUser',current_user.id)
        if exceeded != False:
            data=json.dumps({'result':False,'title':'New user add quota exceeded.','text':'User '+form_data['name']+' can\'t be created. '+str(exceeded),'icon':'warning','type':'error'})
            socketio.emit('add_form_result',
                            data,
                            namespace='/isard-admin/sio_admins', 
                            room='user_'+current_user.id)
            return

        res=app.adminapi.user_add(form_data)
        if res is True:
            data=json.dumps({'result':True,'title':'New user','text':'User '+form_data['name']+' has been created...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'New user','text':'User '+form_data['name']+' can\'t be created. Maybe it already exists!','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room='users')
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room=current_user.category+'_users')


@socketio.on('user_edit', namespace='/isard-admin/sio_admins')
def socketio_user_edit(form_data):
    if current_user.role == 'admin' or current_user.role == 'manager': 
        res=app.adminapi.user_edit(form_data)
        if res is True:
            data=json.dumps({'result':True,'title':'User edit','text':'User '+form_data['name']+' has been updated...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'User edit','text':'User '+form_data['name']+' can\'t be updated!','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room='users')
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room=current_user.category+'_users')

@socketio.on('user_passwd', namespace='/isard-admin/sio_admins')
def socketio_user_passwd(form_data):
    if current_user.role == 'admin' or current_user.role == 'manager': 
        res=app.adminapi.user_passwd(form_data)
        if res is True:
            data=json.dumps({'result':True,'title':'User edit','text':'User '+form_data['name']+' has been updated...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'User edit','text':'User '+form_data['name']+' can\'t be updated!','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room='users')
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room=current_user.category+'_users')

@socketio.on('user_delete', namespace='/isard-admin/sio_admins')
def socketio_user_delete(id):
    if current_user.role == 'admin' or current_user.role == 'manager': 
        res=app.adminapi.user_delete(id)
        if res is True:
            data=json.dumps({'result':True,'title':'Delete user','text':'User '+id+' has been deleted...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'Delete user','text':'User '+id+' can\'t be deleted.','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room='users')    
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room=current_user.category+'_users')

@socketio.on('category_delete', namespace='/isard-admin/sio_admins')
def socketio_category_delete(id):
    if current_user.role == 'admin': 
        res=app.adminapi.category_delete(id)
        if res is True:
            data=json.dumps({'result':True,'title':'Delete category','text':'Category '+id+' has been deleted...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'Delete category','text':'Category '+id+' can\'t be deleted.','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room='users')    
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room=current_user.category+'_users')

@socketio.on('group_delete', namespace='/isard-admin/sio_admins')
def socketio_group_delete(id):
    if current_user.role == 'admin' or current_user.role == 'manager': 
        res=app.adminapi.group_delete(id)
        if res is True:
            data=json.dumps({'result':True,'title':'Delete group','text':'Group '+id+' has been deleted...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'Delete group','text':'Group '+id+' can\'t be deleted.','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room='users')    
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room=current_user.category+'_users')

@socketio.on('bulkusers_add', namespace='/isard-admin/sio_admins')
def socketio_bulkuser_add(form_data):
    if current_user.role == 'admin' or current_user.role == 'manager': 
        data=form_data['data']
        users=form_data['users']
        stripped_users=[]
        for user in users:
            #stripped_users.append({k.encode("latin1").rstrip(): v.encode("latin1").rstrip() for k,v in user.items()})
            u=dict(map(str.strip,x) for x in user.items())
            #u=dict(map(str.encode('utf-8'),x) for x in u.items())
            stripped_users.append(u)
        users=stripped_users
        exceeded = quotas.check('NewUsers',current_user.id, amount=len(users))
        if exceeded != False:
            data=json.dumps({'result':False,'title':'New bulk user add quota exceeded.','text':str(len(users))+' users can\'t be created. '+str(exceeded),'icon':'warning','type':'error'})
            socketio.emit('add_form_result',
                            data,
                            namespace='/isard-admin/sio_admins', 
                            room='user_'+current_user.id)
            return

        final_users=[{**u, **data} for u in users]
        res=app.adminapi.users_add(final_users)
        if res is True:
            data=json.dumps({'result':True,'title':'New user','text':'A total of '+str(len(final_users))+' users has been created...','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'New user','text':'Something went wrong when creating '+str(len(final_users))+' can\'t be created. Maybe they already exists!','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room='users')                    
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room=current_user.category+'_users')

@socketio.on('user_toggle', namespace='/isard-admin/sio_admins')
def socketio_user_toggle(data):
    if current_user.role == 'admin' or current_user.role == 'manager': 
        # ~ remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
        res=app.adminapi.user_toggle_active(data['pk'])
        if res is True:
            info=json.dumps({'result':True,'title':'User enable/disable','text':'User '+data['name']+' enable/disable success.','icon':'success','type':'success'})
        else:
            info=json.dumps({'result':False,'title':'User enable/disable','text':'User '+data['name']+' could not toggle enable status!','icon':'warning','type':'error'})        
        socketio.emit('result',
                        info,
                        namespace='/isard-admin/sio_admins', 
                        room='users')
        socketio.emit('result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room=current_user.category+'_users')

@socketio.on('role_category_group_add', namespace='/isard-admin/sio_admins')
def socketio_role_category_group_add(form_data):
    if current_user.role == 'manager':
        if form_data['table'] in ['categories','roles']:
            data=json.dumps({'result':False,'title':'Not allowed.','icon':'warning','type':'error'})
            socketio.emit('add_form_result',
                            data,
                            namespace='/isard-admin/sio_admins', 
                            room='users')
            socketio.emit('add_form_result',
                            data,
                            namespace='/isard-admin/sio_admins', 
                            room=current_user.category+'_users')
            return

    if current_user.role == 'admin' or current_user.role == 'manager': 
        dict=app.isardapi.f.unflatten_dict(form_data)
        res=app.adminapi.rcg_add(dict,current_user)
        if res is True:
            data=json.dumps({'result':True,'title':'New '+form_data['table'],'text':'Added new '+form_data['table']+': '+form_data['name'],'icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'New '+form_data['table'],'text':form_data['name']+' can\'t be created. Maybe it already exists!','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room='users')
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room=current_user.category+'_users')

@socketio.on('quota_update', namespace='/isard-admin/sio_admins')
def socketio_quota_update(form_data):
    if current_user.role == 'manager':
        if form_data['table'] in ['categories','roles']:
            data=json.dumps({'result':False,'title':'Not allowed.','text':'Not enough privileges','icon':'warning','type':'error'})
            socketio.emit('add_form_result',
                            data,
                            namespace='/isard-admin/sio_admins', 
                            room='users')
            socketio.emit('add_form_result',
                            data,
                            namespace='/isard-admin/sio_admins', 
                            room=current_user.category+'_users')
            return

    if current_user.role == 'admin' or current_user.role == 'manager': 
        res=app.adminapi.rcg_quota_update(form_data)
        if res is True:
            data=json.dumps({'result':True,'title':'Update quota','text':'Updated correctly.','icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'Update quota','text':'Error on updating!','icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room='users')
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room=current_user.category+'_users')

## Domains namespace
@socketio.on('connect', namespace='/isard-admin/sio_users')
def socketio_users_connect():
    join_room('user_'+current_user.id)
    socketio.emit('user_quota', 
                    json.dumps(quotas.get(current_user.id)), 
                    namespace='/isard-admin/sio_users', 
                    room='user_'+current_user.id)
    
@socketio.on('disconnect', namespace='/isard-admin/sio_users')
def socketio_domains_disconnect():
    None

'''
DOMAINS
'''
@socketio.on('domain_add', namespace='/isard-admin/sio_users')
def socketio_domains_add(form_data):
    exceeded = quotas.check('NewDesktop',current_user.id)
    if exceeded != False:
        data=json.dumps({'result':False,'title':'New desktop quota exceeded.','text':'Desktop '+create_dict['name']+' can\'t be created. '+str(exceeded),'icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_users', 
                        room='user_'+current_user.id)
        return

    create_dict=app.isardapi.f.unflatten_dict(form_data)
    
    create_dict=parseHardware(create_dict)
    create_dict=quotas.limit_user_hardware_allowed(create_dict,current_user.id)

    res=app.isardapi.new_domain_from_tmpl(current_user.id, create_dict)

    if res == True:
        data=json.dumps({'result':True,'title':'New desktop','text':'Desktop '+create_dict['name']+' is being created...','icon':'success','type':'success'})
    else:
        data=json.dumps({'result':False,'title':'New desktop','text':'Desktop '+create_dict['name']+' can\'t be created. '+str(res),'icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    data,
                    namespace='/isard-admin/sio_users', 
                    room='user_'+current_user.id)

@socketio.on('domain_edit', namespace='/isard-admin/sio_users')
def socketio_domain_edit(form_data):
    #~ Check if user has quota and rights to do it
    #~ if current_user.role=='admin':
        #~ None
    create_dict=app.isardapi.f.unflatten_dict(form_data)  
    create_dict=parseHardware(create_dict)     
    create_dict=quotas.limit_user_hardware_allowed(create_dict,current_user.id)

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
                    namespace='/isard-admin/sio_users', 
                    room='user_'+current_user.id)

@socketio.on('domain_template_add', namespace='/isard-admin/sio_users')
def socketio_domain_template_add(form_data):
    exceeded = quotas.check('NewTemplate',current_user.id)
    if exceeded != False:
        data=json.dumps({'result':False,'title':'New template quota exceeded.','text':'Template '+form_data['name']+' can\'t be created. '+str(exceeded),'icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_users', 
                        room='user_'+current_user.id)
        return

    partial_tmpl_dict=app.isardapi.f.unflatten_dict(form_data)
    partial_tmpl_dict=parseHardware(partial_tmpl_dict)
    partial_tmpl_dict=quotas.limit_user_hardware_allowed(partial_tmpl_dict,current_user.id)
    partial_tmpl_dict['create_dict']['hardware']={**partial_tmpl_dict['hardware'], **partial_tmpl_dict['create_dict']['hardware']}
    partial_tmpl_dict.pop('hardware',None)
    from_id=partial_tmpl_dict['id']
    partial_tmpl_dict.pop('id',None)

    res=app.isardapi.new_tmpl_from_domain(from_id, partial_tmpl_dict, current_user.id)
    if res == True:
        data=json.dumps({'result':True,'title':'New template','text':'Template '+partial_tmpl_dict['name']+' is being created...','icon':'success','type':'success'})
    elif res == 'Template name already exists.':
        data=json.dumps({'result':False,'title':'New template','text':'Template '+partial_tmpl_dict['name']+' can\'t be created as it already exists. '+str(res),'icon':'warning','type':'error'})
    else:
        data=json.dumps({'result':False,'title':'New template','text':'Template '+partial_tmpl_dict['name']+' can\'t be created. '+str(res),'icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    data,
                    namespace='/isard-admin/sio_users', 
                    room='user_'+current_user.id)

@socketio.on('domain_template_add', namespace='/isard-admin/sio_admins')
def socketio_admin_domain_template_add(form_data):
    partial_tmpl_dict=app.isardapi.f.unflatten_dict(form_data)
    partial_tmpl_dict=parseHardware(partial_tmpl_dict)
    partial_tmpl_dict=quotas.limit_user_hardware_allowed(partial_tmpl_dict,current_user.id)
    partial_tmpl_dict['create_dict']['hardware']={**partial_tmpl_dict['hardware'], **partial_tmpl_dict['create_dict']['hardware']}
    partial_tmpl_dict.pop('hardware',None)
    from_id=partial_tmpl_dict['id']
    partial_tmpl_dict.pop('id',None)

    res=app.isardapi.new_tmpl_from_domain(from_id, partial_tmpl_dict, current_user.id)

    if res == True:
        data=json.dumps({'result':True,'title':'New template','text':'Template '+partial_tmpl_dict['name']+' is being created...','icon':'success','type':'success'})
    else:
        data=json.dumps({'result':False,'title':'New template','text':'Template '+partial_tmpl_dict['name']+' can\'t be created. '+str(res),'icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    data,
                    namespace='/isard-admin/sio_admins', 
                    room='domains')
                                        
@socketio.on('domain_update', namespace='/isard-admin/sio_users')
def socketio_domains_update(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    socketio.emit('result',
                    app.isardapi.update_table_status(current_user.id, 'domains', data,remote_addr),
                    namespace='/isard-admin/sio_users', 
                    room='user_'+current_user.id)

@socketio.on('domain_update', namespace='/isard-admin/sio_admins')
def socketio_admin_domains_update(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    socketio.emit('result',
                    app.isardapi.update_table_status(current_user.id, 'domains', data,remote_addr),
                    namespace='/isard-admin/sio_admins', 
                    room='domains')
                    
@socketio.on('domain_edit', namespace='/isard-admin/sio_admins')
def socketio_admins_domain_edit(form_data):
    #~ Check if user has quota and rights to do it
    #~ if current_user.role=='admin':
        #~ None
    create_dict=app.isardapi.f.unflatten_dict(form_data)
    create_dict=parseHardware(create_dict)
    create_dict=quotas.limit_user_hardware_allowed(create_dict,current_user.id)
    create_dict['create_dict']={'hardware':create_dict['hardware'].copy()}
    create_dict.pop('hardware',None)
    res=app.isardapi.update_domain(create_dict.copy())
    if res is True:
        data=json.dumps({'id':create_dict['id'], 'result':True,'title':'Updated desktop','text':'Desktop '+create_dict['name']+' has been updated...','icon':'success','type':'success'})
    else:
        data=json.dumps({'id':create_dict['id'], 'result':True,'title':'Updated desktop','text':'Desktop '+create_dict['name']+' can\'t be updated.','icon':'warning','type':'error'})
    socketio.emit('edit_form_result',
                    data,
                    namespace='/isard-admin/sio_admins', 
                    room='domains')

#### NOT USED NOW
@socketio.on('domain_bulkedit', namespace='/isard-admin/sio_admins')
def socketio_admins_domain_bulkedit(form_data):
    create_dict=app.isardapi.f.unflatten_dict(form_data)
    create_dict=parseHardware(create_dict)
    create_dict=quotas.limit_user_hardware_allowed(create_dict,current_user.id)
    create_dict['create_dict']={'hardware':create_dict['hardware'].copy()}
    create_dict.pop('hardware',None)
    res=app.adminapi.domains_update(create_dict.copy())
    if res is True:
        data=json.dumps({'id':create_dict['ids'], 'result':True,'title':'Updated desktops','text':'Desktop '+str(create_dict['ids'])+' has been updated...','icon':'success','type':'success'})
    else:
        data=json.dumps({'id':create_dict['ids'], 'result':False,'title':'Updated desktops','text':'Desktop '+str(create_dict['ids'])+' can\'t be updated.','icon':'warning','type':'error'})
    socketio.emit('edit_form_result',
                    data,
                    namespace='/isard-admin/sio_admins', 
                    room='domains')

def parseHardwareFromIso(create_dict):
    if 'boot_order' not in create_dict['hardware'].keys():
        try:
            create_dict['hardware']['boot_order']=[app.isardapi.get_alloweds(current_user.id,'boots',pluck=['id'])[0]['id']]
        except:
            create_dict['hardware']['boot_order']=['iso']
    else:
        create_dict['hardware']['boot_order']=[create_dict['hardware']['boot_order']]

    if 'interfaces' not in create_dict['hardware'].keys():
        try:
            create_dict['hardware']['interfaces']=[app.isardapi.get_alloweds(current_user.id,'interfaces',pluck=['id'])[0]['id']]
        except:
            create_dict['hardware']['interfaces']=['default']
    else:
        create_dict['hardware']['interfaces']=[create_dict['hardware']['interfaces']]

    if 'graphics' not in create_dict['hardware'].keys():
        try:
            create_dict['hardware']['graphics']=[app.isardapi.get_alloweds(current_user.id,'graphics',pluck=['id'])[0]['id']]
        except:
            create_dict['hardware']['graphics']=['default']
    else:
        create_dict['hardware']['graphics']=[create_dict['hardware']['graphics']]

    if 'videos' not in create_dict['hardware'].keys():
        try:
            create_dict['hardware']['videos']=[app.isardapi.get_alloweds(current_user.id,'videos',pluck=['id'])[0]['id']]
        except:
            create_dict['hardware']['videos']=['default']
    else:
        create_dict['hardware']['videos']=[create_dict['hardware']['videos']]

    if 'hypervisors_pools' not in create_dict.keys():
        try:
            create_dict['hypervisors_pools']=[app.isardapi.get_alloweds(current_user.id,'hypervisors_pools',pluck=['id'])[0]['id']]
        except:
            create_dict['hypervisors_pools']=['default']
    else:
        create_dict['hypervisors_pools']=[create_dict['hypervisors_pools']]

    if 'forced_hyp' not in create_dict.keys():
            create_dict['forced_hyp']=False
    else:
        None # use passed forced_hyp from form

    if 'memory' not in create_dict['hardware'].keys():
            create_dict['hardware']['memory']=int(1.5*1048576)
    else:
        create_dict['hardware']['memory']=int(float(create_dict['hardware']['memory'])*1048576)

    if 'vcpus' not in create_dict['hardware'].keys():
            create_dict['hardware']['vcpus']=1
    else:
        create_dict['hardware']['vcpus']=int(create_dict['hardware']['vcpus'])

    return create_dict 

def parseHardware(create_dict):
    original_create_dict={}
    ## Generate from original domain:
    if 'template' in create_dict:
        data=app.isardapi.get_domain(create_dict['template'], human_size=False, flatten=False)
    else:
        data=app.isardapi.get_domain(create_dict['id'], human_size=False, flatten=False)
    original_create_dict['hardware']=data['create_dict']['hardware']
    original_create_dict['hardware'].pop('disks',None)
    original_create_dict['hypervisors_pools']=data['hypervisors_pools']

    if 'hardware' not in create_dict.keys():
        return original_create_dict

    create_dict['hardware']['vcpus']=int(create_dict['hardware']['vcpus']) if 'vcpus' in create_dict['hardware'].keys() else int(original_create_dict['hardware']['vcpus'])
    create_dict['hardware']['memory']=int(float(create_dict['hardware']['memory'])*1048576) if 'memory' in create_dict['hardware'].keys() else int(float(original_create_dict['hardware']['memory']))
    create_dict['hardware']['graphics']=[create_dict['hardware']['graphics']] if 'graphics' in create_dict['hardware'].keys() else original_create_dict['hardware']['graphics']
    create_dict['hardware']['videos']=[create_dict['hardware']['videos']] if 'videos' in create_dict['hardware'].keys() else original_create_dict['hardware']['videos']
    create_dict['hardware']['boot_order']=[create_dict['hardware']['boot_order']] if 'boot_order' in create_dict['hardware'].keys() else original_create_dict['hardware']['boot_order']
    create_dict['hardware']['interfaces']=create_dict['hardware']['interfaces'] if 'interfaces' in create_dict['hardware'].keys() else original_create_dict['hardware']['interfaces']
    create_dict['hardware']['qos_id']=create_dict['hardware']['qos_id'] if 'qos_id' in create_dict['hardware'].keys() else original_create_dict['hardware']['qos_id'] if 'qos_id' in original_create_dict['hardware'].keys() else False
    create_dict['hypervisors_pools']=[create_dict['hypervisors_pools']] if 'hypervisors_pools' in create_dict else original_create_dict['hypervisors_pools']
    
    """ if 'forced_hyp' in create_dict.keys():
        create_dict['forced_hyp']=[create_dict['forced_hyp']]
    elif 'forced_hyp' in original_create_dict['forced_hyp'].keys()
        create_dict['forced_hyp']=original_create_dict['forced_hyp']
    else
        create_dict['forced_hyp']=False """
    create_dict['forced_hyp']=[create_dict['forced_hyp']] if 'forced_hyp' in create_dict.keys() else (original_create_dict['forced_hyp'] if 'forced_hyp' in original_create_dict.keys() else False)

    return create_dict

@socketio.on('domain_viewer', namespace='/isard-admin/sio_users')
def socketio_domains_viewer(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    if 'preferred' in data.keys():
        if data['preferred']:
            default_viewer=data['kind']
        else:
            default_viewer=False
    viewer_data=isardviewer.viewer_data(data['pk'],get_viewer=data['kind'],default_viewer=default_viewer,current_user=current_user)
    if viewer_data:
        socketio.emit('domain_viewer',
                        json.dumps(viewer_data),
                        namespace='/isard-admin/sio_users', 
                        room='user_'+current_user.id)          
        
    else:
        msg=json.dumps({'result':True,'title':'Viewer','text':'Viewer could not be opened. Try again.','icon':'warning','type':'error'})
        socketio.emit('result',
                        msg,
                        namespace='/isard-admin/sio_users', 
                        room='user_'+current_user.id)     

@socketio.on('domain_viewer', namespace='/isard-admin/sio_admins')
def socketio_admin_domains_viewer(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    viewer_data=isardviewer.viewer_data(data['pk'],get_viewer=data['kind'])
    if viewer_data:
        socketio.emit('domain_viewer',
                        json.dumps(viewer_data),
                        namespace='/isard-admin/sio_admins', 
                        room='user_'+current_user.id)          
        
    else:
        msg=json.dumps({'result':True,'title':'Viewer','text':'Viewer could not be opened. Try again.','icon':'warning','type':'error'})
        socketio.emit('result',
                        msg,
                        namespace='/isard-admin/sio_users', 
                        room='user_'+current_user.id)   

@socketio.on('disposable_viewer', namespace='/isard-admin/sio_disposables')
def socketio_disposables_viewer(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    # ~ viewer_data=isardviewer.get_viewer(data,current_user,remote_addr)
    viewer_data=isardviewer.viewer_data(data['pk'],get_viewer=data['kind'],default_viewer=default_viewer,current_user=current_user)
    if viewer_data:
        socketio.emit('disposable_viewer',
                        json.dumps(viewer_data),
                        namespace='/isard-admin/sio_disposables', 
                        room='disposable_'+remote_addr)           
        
    else:
        msg=json.dumps({'result':True,'title':'Viewer','text':'Viewer could not be opened. Try again.','icon':'warning','type':'error'})
        socketio.emit('result',
                        msg,
                        namespace='/isard-admin/sio_disposables', 
                        room='disposable_'+remote_addr)      
    
    
    
    
    
    
    
    
    
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
                                                     
'''
MEDIA
'''
@socketio.on('media_update', namespace='/isard-admin/sio_admins')
def socketio_admin_media_update(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    socketio.emit('result',
                    app.isardapi.update_table_status(current_user.id, 'media', data,remote_addr),
                    namespace='/isard-admin/sio_admins', 
                    room='media')
                    
    
@socketio.on('media_update', namespace='/isard-admin/sio_users')
def socketio_media_update(data):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    socketio.emit('result',
                    app.isardapi.update_table_status(current_user.id, 'media', data,remote_addr),
                    namespace='/isard-admin/sio_users', 
                    room='user_'+current_user.id)  
       

@socketio.on('media_add', namespace='/isard-admin/sio_admins')
def socketio_admin_media_add(form_data):
    form_data['hypervisors_pools']=[form_data['hypervisors_pools']]
    res=app.adminapi.media_add(current_user.id, form_data)
    if res == True:
        info=json.dumps({'result':True,'title':'New media','text':'Media is being downloaded...','icon':'success','type':'success'})
    else:
        info=json.dumps({'result':False,'title':'New media','text':'Media can\'t be created. '+str(res),'icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    info,
                    namespace='/isard-admin/sio_admins', 
                    room='media')

@socketio.on('media_add', namespace='/isard-admin/sio_users')
def socketio_media_add(form_data):
    exceeded = quotas.check('NewIso',current_user.id)
    if exceeded != False:
        data=json.dumps({'result':False,'title':'New media quota exceeded.','text':'Media '+form_data['name']+' can\'t be created. '+str(exceeded),'icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_users', 
                        room='user_'+current_user.id)
        return

    form_data['hypervisors_pools']=[form_data['hypervisors_pools']]
    res=app.adminapi.media_add(current_user.id, form_data)
    if res == True:
        info=json.dumps({'result':True,'title':'New media','text':'Media is being downloaded...','icon':'success','type':'success'})
    else:
        info=json.dumps({'result':False,'title':'New media','text':'Media can\'t be created. '+str(res),'icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    info,
                    namespace='/isard-admin/sio_users', 
                    room='user_'+current_user.id)


@socketio.on('domain_media_add', namespace='/isard-admin/sio_admins')
def socketio_admin_domains_media_add(form_data):
    exceeded = quotas.check('NewDesktop',current_user.id)
    if exceeded != False:
        data=json.dumps({'result':False,'title':'New desktop quota exceeded.','text':'Desktop '+create_dict['name']+' can\'t be created. '+str(exceeded),'icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_users', 
                        room='user_'+current_user.id)
        return
            
    create_dict=app.isardapi.f.unflatten_dict(form_data)
    create_dict=parseHardwareFromIso(create_dict)

    create_dict['create_from_virt_install_xml']=create_dict.pop('install','')
    disk_size=create_dict.pop('disk_size','15')+'G'
    name=create_dict.pop('name','')
    description=create_dict.pop('description','None')
    hyper_pools=create_dict.pop('hypervisors_pools',['default'])
    # ~ icon=create_dict['icon']
    icon=create_dict.pop('icon','circle-o')
    create_dict.pop('allowed',None)
    res=app.adminapi.domain_from_media(current_user.id, name, description, icon, create_dict, hyper_pools, disk_size)
    if res is True:
        info=json.dumps({'result':True,'title':'New desktop','text':'Desktop '+name+' is being created...','icon':'success','type':'success'})
    else:
        info=json.dumps({'result':False,'title':'New desktop','text':'Desktop '+name+' can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    info,
                    namespace='/isard-admin/sio_admins', 
                    room='user_'+current_user.id)

@socketio.on('domain_media_add', namespace='/isard-admin/sio_users')
def socketio_domains_media_add(form_data):
    exceeded = quotas.check('NewDesktop',current_user.id)
    if exceeded != False:
        data=json.dumps({'result':False,'title':'New desktop quota exceeded.','text':'Desktop '+create_dict['name']+' can\'t be created. '+str(exceeded),'icon':'warning','type':'error'})
        socketio.emit('add_form_result',
                        data,
                        namespace='/isard-admin/sio_users', 
                        room='user_'+current_user.id)
        return

    create_dict=app.isardapi.f.unflatten_dict(form_data)
    create_dict=parseHardwareFromIso(create_dict)

    create_dict['create_from_virt_install_xml']=create_dict.pop('install','')
    disk_size=create_dict.pop('disk_size','15')+'G'
    name=create_dict.pop('name','')
    description=create_dict.pop('description','None')
    hyper_pools=create_dict.pop('hypervisors_pools',['default'])
    # ~ icon=create_dict['icon']
    icon=create_dict.pop('icon','circle-o')
    create_dict.pop('allowed',None)
    res=app.adminapi.domain_from_media(current_user.id, name, description, icon, create_dict, hyper_pools, disk_size)
    if res is True:
        info=json.dumps({'result':True,'title':'New desktop','text':'Desktop '+name+' is being created...','icon':'success','type':'success'})
    else:
        info=json.dumps({'result':False,'title':'New desktop','text':'Desktop '+name+' can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    info,
                    namespace='/isard-admin/sio_users', 
                    room='user_'+current_user.id)
                    

## Resources
@socketio.on('resources_insert_update', namespace='/isard-admin/sio_admins')
def socketio_admin_resources_update(data):
    if current_user.role == 'admin': 
        table=data.pop("table")
        if data['id']==False:
            #Insert
            insert=True
            data['id']=app.isardapi.parse_string(data['name'])
            res = app.adminapi.insert_table_dict(table, data)
        else:
            # Update
            insert=False
            id=data.pop("id")
            res = app.adminapi.update_table_dict(table, id, data)

        if res:
            data=json.dumps({'result':True,'title':'Update '+table,'text':'Updated for '+data['name'],'icon':'success','type':'success'})
        else:
            data=json.dumps({'result':False,'title':'Update '+table,'text':'Something went wrong. Could not update!','icon':'warning','type':'error'})
        socketio.emit('result' if res == False else 'add_form_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room='user_'+current_user.id)

## Alloweds
@socketio.on('allowed_update', namespace='/isard-admin/sio_admins')
def socketio_admin_allowed_update(data):
    if current_user.role == 'admin' or current_user.role == 'manager': 
        res = app.adminapi.update_table_dict(data['table'], data['id'],{'allowed':data['allowed']})
        if res:
            data=json.dumps({'result':True,'title':'Update permissions','text':'Permissions updated for '+data['id'],'icon':'success','type':'success'})
        else:
            data=json.dumps({'result':True,'title':'Update permissions','text':'Something went wrong. Could not update permissions!','icon':'warning','type':'error'})
        socketio.emit('allowed_result',
                        data,
                        namespace='/isard-admin/sio_admins', 
                        room='user_'+current_user.id)

@socketio.on('allowed_update', namespace='/isard-admin/sio_users')
def socketio_allowed_update(data):
    res = app.adminapi.update_table_dict(data['table'], data['id'],{'allowed':data['allowed']})
    if res:
        info=json.dumps({'result':data,'title':'Update permissions','text':'Permissions updated for '+data['id'],'icon':'success','type':'success'})
    else:
        info=json.dumps({'result':False,'title':'Update permissions','text':'Something went wrong. Could not update permissions!','icon':'warning','type':'error'})
    socketio.emit('allowed_result',
                    info,
                    namespace='/isard-admin/sio_users', 
                    room='user_'+current_user.id)

                
                
                    
## Admin namespace
@socketio.on('connect', namespace='/isard-admin/sio_admins')
def socketio_admins_connect():
    if current_user.role=='admin':
        join_room('admins')
        join_room('user_'+current_user.id)
        socketio.emit('user_quota', 
                        json.dumps(quotas.get(current_user.id)), 
                        namespace='/isard-admin/sio_admins', 
                        room='user_'+current_user.id)
    elif current_user.role=='manager':
        join_room('user_'+current_user.id)
        socketio.emit('user_quota', 
                        json.dumps(quotas.get(current_user.id)), 
                        namespace='/isard-admin/sio_admins', 
                        room='user_'+current_user.id)        
    else:
        None

@socketio.on('join_rooms', namespace='/isard-admin/sio_admins')
def socketio_admins_joinrooms(join_rooms):
    if current_user.role=='admin':
        for rm in join_rooms:
            join_room(rm)
    if current_user.role =='manager':
        for rm in join_rooms:
            join_room(current_user.category+'_'+rm)
            log.debug('USER: '+current_user.id+' JOINED ROOM: '+current_user.category+'_'+rm)

@socketio.on('domain_virtbuilder_add', namespace='/isard-admin/sio_admins')
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
    res=app.adminapi.domain_from_virtbuilder(current_user.id, name, description, icon, create_dict, hyper_pools, disk_size)
    if res is True:
        info=json.dumps({'result':True,'title':'New desktop','text':'Desktop '+name+' is being created...','icon':'success','type':'success'})
    else:
        info=json.dumps({'result':False,'title':'New desktop','text':'Desktop '+name+' can\'t be created.','icon':'warning','type':'error'})
    socketio.emit('add_form_result',
                    info,
                    namespace='/isard-admin/sio_admins', 
                    room='user_'+current_user.id)


    



@socketio.on('scheduler_add', namespace='/isard-admin/sio_admins')
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
                    namespace='/isard-admin/sio_admins', 
                    room='config')

                    
@socketio.on('disconnect', namespace='/isard-admin/sio_admins')
def socketio_admins_disconnect():
    leave_room('admins')
    try:
        leave_room('user_'+current_user.id)
    except Exception as e:
        log.debug('USER leaved without disconnect')
 

