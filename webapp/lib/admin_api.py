# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
from decimal import Decimal
import random, queue
from threading import Thread
import time
from webapp import app
from werkzeug import secure_filename
import os
from datetime import datetime, timedelta
import rethinkdb as r

from ..lib.log import * 

from .flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)


class isardAdmin():
    def __init__(self):
        self.f=flatten()


    def check(self,dict,action):
        #~ These are the actions:
        #~ {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
        if dict[action]: 
            return True
        if not dict['errors']: return True
        return False

    import socket
    from contextlib import closing

    def check_socket(host, port):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            if sock.connect_ex((host, port)) == 0:
                return True
            else:
                return False
                    
    '''
    ADMIN API
    '''
    def delete_table_key(self,table,key):
        with app.app_context():
            return self.check(r.table(table).get(key).delete().run(db.conn),'deleted')
            
    def toggle_hypervisor_field(self,id,key):
        with app.app_context():
            field=r.table('hypervisors').get(id).run(db.conn)[key]
            new_field=False if field else True
            return self.check(r.table('hypervisors').get(id).update({key:new_field}).run(db.conn),'replaced')

    def multiple_action(self, table, action, ids):
        with app.app_context():
            if action == 'toggle':
                domains_stopped=self.multiple_check_field('domains','status','Stopped',ids)
                domains_started=self.multiple_check_field('domains','status','Started',ids)
                res_stopped=r.table(table).get_all(r.args(domains_stopped)).update({'status':'Starting'}).run(db.conn)
                res_started=r.table(table).get_all(r.args(domains_started)).update({'status':'Stopping'}).run(db.conn)
                return True
            if action == 'delete':
                domains_stopped=self.multiple_check_field('domains','status','Stopped',ids)
                res_deleted=r.table(table).get_all(r.args(domains_stopped)).update({'status':'Deleting'}).run(db.conn)
                return True
            if action == 'force_failed':
                res_deleted=r.table(table).get_all(r.args(ids)).update({'status':'Failed'}).run(db.conn)
                return True
            if action == 'force_stopped':
                res_deleted=r.table(table).get_all(r.args(ids)).update({'status':'Stopped'}).run(db.conn)
                return True
                
    def multiple_check_field(self, table, field, value, ids):
        with app.app_context():
            return [d['id'] for d in list(r.table(table).get_all(r.args(ids)).filter({field:value}).pluck('id').run(db.conn))]
                                    
    def get_admin_user(self):
        with app.app_context():
            ## ALERT: Should remove password (password='')
            return self.f.table_values_bstrap(r.table('users').run(db.conn))

    def get_admin_table(self, table, pluck=False, id=False):
        with app.app_context():
            if id and not pluck:
                return r.table(table).get(id).run(db.conn)
            if pluck and not id:
                return self.f.table_values_bstrap(r.table(table).pluck(pluck).run(db.conn))
            if pluck and id:
                return r.table(table).get(id).pluck(pluck).run(db.conn)           
            return self.f.table_values_bstrap(r.table(table).run(db.conn))
                        
    def get_admin_domains(self):
        with app.app_context():
            listdict=self.f.table_values_bstrap(r.table('domains').run(db.conn))
        i=0
        while i<len(listdict):
            if 'xml' in listdict[i]: del listdict[i]['xml']
            if 'status' not in list(listdict[i].keys()): listdict[i]['status']='template'
            if 'user' not in list(listdict[i].keys()): listdict[i]['user']='admin'
            if 'category' not in list(listdict[i].keys()): listdict[i]['category']='admin'
            if 'group' not in list(listdict[i].keys()): listdict[i]['group']='admin'
            i=i+1
        return listdict

    def get_admin_hypervisors(self, id=False):
        with app.app_context():
            if id:
                listdict = self.f.flatten_dict(r.table('hypervisors').get(id).run(db.conn))
                print(listdict)
            else:
                listdict = self.f.table_values_bstrap(r.table('hypervisors').run(db.conn))
            
                i=0
                while i<len(listdict):
                    if 'fail_connected_reason' not in listdict[i]: listdict[i]['fail_connected_reason']=''
                    if 'disk_operations' not in listdict[i]: listdict[i]['disk_operations']='False'
                    i=i+1
        return listdict            

    def get_admin_pools(self, flat=True):
        with app.app_context():
            if flat:
                return self.f.table_values_bstrap(r.table('hypervisors_pools').run(db.conn))
            else:
                return list(r.table('hypervisors_pools').run(db.conn))

    def insert_table_dict(self, table, dict):
        with app.app_context():
            return self.check(r.table(table).insert(dict).run(db.conn), 'inserted')
                            
    def update_table_dict(self, table, id, dict):
        with app.app_context():
            return self.check(r.table(table).get(id).update(dict).run(db.conn), 'replaced')

    def get_admin_domain_datatables(self):
        with app.app_context():
            return {'columns':self.f.table_header_bstrap('domains'), 'data': self.f.table_values_bstrap('domains', fields)}


    def get_admin_networks(self):
        with app.app_context():
            return list(r.table('interfaces').order_by('name').run(db.conn))

    def add_hypervisor(self,dict):
        with app.app_context():
            return self.check(r.table('hypervisors').insert(dict).run(db.conn),'inserted')

    def add_hypervisor_pool(self,dict):
        with app.app_context():
            return self.check(r.table('hypervisors_pools').insert(dict).run(db.conn),'inserted')

    def removeHypervisor(self,id):
        with app.app_context():
            r.table('hypervisors_events').filter({'hyp_id':id}).delete().run(db.conn)
            r.table('hypervisors_status').filter({'hyp_id':id}).delete().run(db.conn)
            r.table('hypervisors').get(id).delete().run(db.conn)
            return True

    def get_admin_config(self, id=None):
        with app.app_context():
            if id is None:
                return self.f.flatten_dict(r.table('config').get(1).run(db.conn))
            else:
                return self.f.flatten_dict(r.table('config').get(1).run(db.conn))
                
    def getUnflatten(self,dict):
        f=flatten()
        return f.unflatten_dict(dict)

    '''
    BACKUP & RESTORE
    '''
    def backup_db(self):
        import tarfile,pickle,os
        id='isard_backup_'+datetime.now().strftime("%Y%m%d-%H%M%S")
        path='./backups/'
        os.makedirs(path,exist_ok=True)
        dict={'id':id,
              'filename':id+'.tar.gz',
              'path':path,
              'description':'',
              'when':time.time(),
              'data':{},
              'status':'Initializing'}
        with app.app_context():
            r.table('backups').insert(dict).run(db.conn)
        skip_tables=['backups','domains_status','hypervisors_events','hypervisors_status']
        isard_db={}
        with app.app_context():
            r.table('backups').get(id).update({'status':'Loading tables'}).run(db.conn)
            for table in r.table_list().run(db.conn):
                if table not in skip_tables:
                    isard_db[table]=list(r.table(table).run(db.conn))
                    #~ dict['data'][table]=r.table(table).count().run(db.conn)
                    r.table('backups').get(id).update({'data':{table:r.table(table).count().run(db.conn)}}).run(db.conn)
        with app.app_context():
            dict=r.table('backups').get(id).run(db.conn)            
            r.table('backups').get(id).update({'status':'Dumping to file'}).run(db.conn)
        with open(path+id+'.rethink', 'wb') as isard_rethink_file:
            pickle.dump(dict, isard_rethink_file)
        with open(path+id+'.json', 'wb') as isard_db_file:
            pickle.dump(isard_db, isard_db_file)
        with app.app_context():
            r.table('backups').get(id).update({'status':'Compressing'}).run(db.conn)
        with tarfile.open(path+id+'.tar.gz', "w:gz") as tar:
            tar.add(path+id+'.json', arcname=os.path.basename(path+id+'.json'))
            tar.add(path+id+'.rethink', arcname=os.path.basename(path+id+'.rethink'))
            tar.close()
        try:
            os.remove(path+id+'.json')
            os.remove(path+id+'.rethink')
        except OSError:
            pass
        with app.app_context():
            r.table('backups').get(id).update({'status':'Finished creating'}).run(db.conn)
            
    def restore_db(self,id):
        import tarfile,pickle
        with app.app_context():
            dict=r.table('backups').get(id).run(db.conn)
            r.table('backups').get(id).update({'status':'Uncompressing backup'}).run(db.conn)
        path=dict['path']
        with tarfile.open(path+id+'.tar.gz', "r:gz") as tar:
            tar.extractall(path)
            tar.close()
        with app.app_context():
            r.table('backups').get(id).update({'status':'Loading data..'}).run(db.conn)
        with open(path+id+'.json', 'rb') as isard_db_file:
            isard_db = pickle.load(isard_db_file)
        for k,v in isard_db.items():
            with app.app_context():
                if not r.table_list().contains(k).run(db.conn):
                    log.error("Table {} not found, should have been created on IsardVDI startup.".format(k))
                    return False
                else:
                    log.info("Restoring table {}".format(k))
                    with app.app_context():
                        r.table('backups').get(id).update({'status':'Updating table: '+k}).run(db.conn)
                    log.info(r.table(k).insert(v, conflict='update').run(db.conn))
        with app.app_context():
            r.table('backups').get(id).update({'status':'Finished restoring'}).run(db.conn)
        try:
            os.remove(path+id+'.json')
            os.remove(path+id+'.rethink')
        except OSError as e:
            log.error(e)
            pass

    def upload_backup(self,handler):
        path='./backups/'
        id=handler.filename.split('.tar.gz')[0]
        filename = secure_filename(handler.filename)
        handler.save(os.path.join(path+filename))
        import tarfile,pickle
        #~ with app.app_context():
            #~ dict=r.table('backups').get(id).run(db.conn)
            #~ r.table('backups').get(id).update({'status':'Uncompressing backup'}).run(db.conn)
        #~ path=dict['path']
        
        with tarfile.open(path+handler.filename, "r:gz") as tar:
            tar.extractall(path)
            tar.close()
        #~ with app.app_context():
            #~ r.table('backups').get(id).update({'status':'Loading data..'}).run(db.conn)
        with open(path+id+'.rethink', 'rb') as isard_rethink_file:
            isard_rethink = pickle.load(isard_rethink_file)
        with app.app_context():
            log.info(r.table('backups').insert(isard_rethink, conflict='update').run(db.conn))
        with app.app_context():
            r.table('backups').get(id).update({'status':'Finished uploading'}).run(db.conn)
        try:
            os.remove(path+id+'.json')
            os.remove(path+id+'.rethink')
        except OSError as e:
            log.error(e)
            pass
        
    def remove_backup_db(self,id):
        with app.app_context():
            dict=r.table('backups').get(id).run(db.conn)
        path=dict['path']
        try:
            os.remove(path+id+'.tar.gz')
        except OSError:
            pass
        with app.app_context():
            r.table('backups').get(id).delete().run(db.conn)

    def info_backup_db(self,id):
        with app.app_context():
            dict=r.table('backups').get(id).run(db.conn)
        with open(dict['path']+dict['filename'], 'rb') as isard_db_file:
            return dict['path'],dict['filename'], isard_db_file.read()
        

    '''
    CLASSROOMS
    '''
    def replace_hosts_viewers_items(self,place,hosts):
        with app.app_context():
            try:
                place['id']=app.isardapi.parse_string(place['name'])
                r.table('places').insert(place, conflict='update').run(db.conn)
            except Exception as e:
                print('error on update place:',e)
                return False
                
            try:
                hosts = [dict(item, place_id=place['id']) for item in hosts]
                hosts = [dict(item, enabled=True) for item in hosts]
                r.table('hosts_viewers').get_all(place['id'], index='place_id').delete().run(db.conn)
                
                return self.check(r.table('hosts_viewers').insert(hosts).run(db.conn),'inserted')
            except Exception as e:
                print('error o update hosts_viewers:',e)
                return False


    def get_hosts_viewers(self, place_id):
        with app.app_context():
            return list(r.table('hosts_viewers').get_all(place_id, index='place_id').run(db.conn))
                    
    '''
    GRAPHS
    '''
    def get_domains_tree(self, id):
        #~ Should verify something???
        with app.app_context():
            rdomains=r.db('isard').table('domains')
            domains=r.table('domains').filter({'create_dict':{'origin':id}}).pluck('id','name').run(db.conn)
            dict={'name':id,'children':[]}
            for d in domains:
                children=r.table('domains').filter({'create_dict':{'origin':d['create_dict']['origin']}}).pluck('id','name').run(db.conn)
                #~ print('children:'+
                #~ children)
                dict['children'].append({'name':d['name'],'size':100})
            return dict
            #~ finished=False
            #~ while not finished:

    def get_domains_tree_list(self):
        #~ Should verify something???
        with app.app_context():
            rdomains=r.db('isard').table('domains').pluck('id','name','kind',{'create_dict':{'origin'}}).run(db.conn)
            domains=[{'id':'isard','kind':'menu','name':'isard'},
                    {'id':'bases','kind':'menu','name':'bases','parent':'isard'},
                    {'id':'base_images','kind':'menu','name':'base_images','parent':'isard'}]
            for d in rdomains:
                if not d['create_dict']['origin']:
                    if d['kind']=='base':
                        domains.append({'id':d['id'],'kind':d['kind'],'name':d['name'],'parent':'bases'})
                    else:
                        domains.append({'id':d['id'],'kind':d['kind'],'name':d['name'],'parent':'base_images'})
                else:
                    domains.append({'id':d['id'],'kind':d['kind'],'name':d['name'],'parent':d['create_dict']['origin']})
                #~ if not d['create_dict']['origin']:
                 #~ print(d['id']+' - '+str(d['create_dict']['origin']))
            return domains
            
    def get_domains_tree_csv(self, id):
        #~ Should verify something???
        with app.app_context():
            rdomains=r.db('isard').table('domains')
            domains=r.table('domains').filter({'create_dict':{'origin':id}}).pluck('id','name').run(db.conn)
            csv='id,value\n'+id+',\n'
            #~ dict={'name':id,'children':[]}
            for d in domains:
                csv=csv+id+'.'+d['id']+',100\n'
                #~ dict['children'].append({'name':d['name'],'size':100})
            print(csv)
            return csv

    def get_dashboard(self):
        with app.app_context():
            return {'users': r.db('isard').table('users').count().run(db.conn),
                    'desktops': r.db('isard').table('domains').get_all('desktop', index='kind').count().run(db.conn),
                    'started': r.db('isard').table('domains').get_all('Started', index='status').count().run(db.conn),
                    'templates': r.db('isard').table('domains').filter(r.row['kind'].match('template')).count().run(db.conn),
                    'isos': r.db('isard').table('isos').count().run(db.conn)}
    '''
    VIRT-BUILDER VIRT-INSTALL
    '''

    def new_domain_from_virtbuilder(self, user, name, description, icon, create_dict, hyper_pools, disk_size):
        with app.app_context():
            userObj=r.table('users').get(user).pluck('id','category','group').run(db.conn)
            #~ import pprint
            #~ pprint.pprint(create_dict)
            create_dict['install']['options']='' #r.table('domains_virt_install').get(create_dict['install']['id']).pluck('options').run(db.conn)['options']
        
        parsed_name = app.isardapi.parse_string(name)
        dir_disk, disk_filename = app.isardapi.get_disk_path(userObj, parsed_name)
        create_dict['hardware']['disks']=[{'file':dir_disk+'/'+disk_filename,
                                            'size':disk_size}]   # 15G as a format
        #~ create_dict['install']['id']=install_id
        #~ create_dict['install']['options']=install_options
        new_domain={'id': '_'+user+'_'+parsed_name,
                  'name': name,
                  'description': description,
                  'kind': 'desktop',
                  'user': userObj['id'],
                  'status': 'CreatingFromBuilder',
                  'detail': None,
                  'category': userObj['category'],
                  'group': userObj['group'],
                  'xml': None,
                  'icon': icon,
                  'server': False,
                  'os': create_dict['builder']['id'],   #### Or name

                  'create_dict': create_dict, 
                  'hypervisors_pools': hyper_pools,
                  'allowed': {'roles': False,
                              'categories': False,
                              'groups': False,
                              'users': False}}
        with app.app_context():
            return self.check(r.table('domains').insert(new_domain).run(db.conn),'inserted')


    def isa_group_separator(self,line):
        return True if line.startswith('[') else False

    def update_virtbuilder(self,url="http://libguestfs.org/download/builder/index"):
        path=app.root_path+'/config/virt/virt-builder-files.ini'
        import requests
        response = requests.get(url)
        file = open(path, "w")
        file.write(response.text)
        file.close()
        import itertools
        images=[]
        with open(path) as f:
            for key,group in itertools.groupby(f,self.isa_group_separator):
                if not key:
                    data={}
                    for item in group:
                        try:
                            if item.startswith(' '): continue
                            field,value=item.split('=')
                            value=value.strip()
                            data[field]=value
                        except Exception as e:
                            continue
                    data['id']=data['file'].split('.xz')[0]
                    if 'revision' not in data: data['revision']='0'
                    images.append(data)
        r.table('domains_virt_builder').insert(images, conflict='update').run(db.conn)
        return True

    def cmd_virtbuilder(self,id,path,size):
        import subprocess
        print('virt-builder '+id+' \
             --output '+path+' \
             --size '+size+'G \
             --format qcow2')
        command_output=subprocess.getoutput(['virt-builder '+id+' \
             --output '+path+' \
             --size '+size+'G \
             --format qcow2'])
        print(command_output)
        return True

    def update_virtinstall(self):
        import subprocess
        data = subprocess.getoutput("osinfo-query os")
        installs=[]
        found=False
        for l in data.split('\n'):
            if not found:
                if '+' in l:
                    found=True
                continue
            else:
                v=l.split('|')
                installs.append({'id':v[0].strip(),'name':v[1].strip(),'vers':v[2].strip(),'www':v[3].strip()})
        r.table('domains_virt_install').insert(installs, conflict='update').run(db.conn)


class flatten(object):
    def __init__(self):
        None

    def table_header_bstrap(self, table, pluck=None, editable=False):
        columns=[]
        for key, value in list(self.flatten_table_keys(table,pluck).items()):
            if editable and key is not 'id':
                columns.append({'field':key,'title':key, 'sortable': True, 'editable': True})
            else:
                columns.append({'field':key,'title':key})
        return columns
        
    def table_values_bstrap(self, rethink_cursor):
        data_in=list(rethink_cursor)
        data_out=[]
        for d in data_in:
            data_out.append(self.flatten_dict(d))
        return data_out
                   
    def flatten_table_keys(self,table,pluck=None):
        with app.app_context():
            if pluck is not None:
                d = r.table(table).pluck(pluck).nth(0).run(db.conn)
            else:
                d = r.table(table).nth(0).run(db.conn)
        def items():
            for key, value in list(d.items()):
                if isinstance(value, dict):
                    for subkey, subvalue in list(self.flatten_dict(value).items()):
                        yield key + "." + subkey, subvalue
                else:
                    yield key, value

        return dict(items())
        
    def flatten_dict(self,d):
        def items():
            for key, value in list(d.items()):
                if isinstance(value, dict):
                    for subkey, subvalue in list(self.flatten_dict(value).items()):
                        yield key + "-" + subkey, subvalue
                else:
                    yield key, value
        return dict(items())

    def unflatten_dict(self,dictionary):
        resultDict = dict()
        for key, value in dictionary.items():
            parts = key.split("-")
            d = resultDict
            for part in parts[:-1]:
                if part not in d:
                    d[part] = dict()
                d = d[part]
            d[parts[-1]] = value
        return resultDict

