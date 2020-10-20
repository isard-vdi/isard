# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
import random, queue
from threading import Thread
import time, json, sys
from webapp import app
from flask_login import current_user
import rethinkdb as r
from ..lib.log import * 

from .flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .admin_api import flatten
from ..auth.authentication import Password  

from netaddr import IPNetwork, IPAddress 

from ..lib.quotas import QuotaLimits
quotas = QuotaLimits()

class isard():
    def __init__(self):
        with app.app_context():
            try:
                self.config=r.table('config').get(1).run(db.conn)
                self.f=flatten()
            except Exception as e:
                log.error('Unable to read config table from RethinkDB isard database')
                log.error('If you need to recreate isard database you should activate wizard again:')
                log.error('   REMOVE install/.wizard file  (rm install/.wizard) and start isard again')
                exit(1)
        pass



    def update_table_status(self,user,table,data,remote_addr):
            # Python 3.9
            # item = table.removesuffix('s').capitalize()
            item = (table.endswith('s') and table[:-1] or table).capitalize()
            with app.app_context():
                dom = r.table(table).get(data['pk']).pluck('status','name','ephimeral').run(db.conn)          
            try:
                if data['name']=='status':
                    if data['value']=='DownloadAborting':
                        if dom['status'] in ['Downloading']:
                            if app.isardapi.update_table_value(table, data['pk'], data['name'], data['value']):
                                return json.dumps({'title':item+' aborting success','text':item+' '+dom['name']+' will be aborted','icon':'success','type':'info'}), 200, {'ContentType':'application/json'}
                            else:
                                return json.dumps({'title':item+' aborting error','text':item+' '+dom['name']+' can\'t be aborted. Something went wrong!','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
                        else:
                            return json.dumps({'title':item+' aborting error','text':item+' '+dom['name']+' can\'t be aborted while not Downloading','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
                    if data['value']=='Stopping':
                        if dom['status'] in ['Started']:
                            if app.isardapi.update_table_value(table, data['pk'], data['name'], data['value']):
                                return json.dumps({'title':False,'text':item+' '+dom['name']+' will be stopped','icon':'success','type':'info'}), 200, {'ContentType':'application/json'}
                            else:
                                return json.dumps({'title':item+' stopping error','text':item+' '+dom['name']+' can\'t be stopped. Something went wrong!','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
                        else:
                            return json.dumps({'title':item+' stopping error','text':item+' '+dom['name']+' can\'t be stopped while not Started','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
                    if data['value']=='Deleting':
                        if table=='media':
                            ''' WE SHOULD CHECK THAT DOMAINS ARE STOPPED '''
                            app.adminapi.media_delete(data['pk'])                        
                            # ~ if dom['status'] in ['Stopped','Failed']:
                            if app.isardapi.update_table_value(table, data['pk'], data['name'], data['value']):
                                return json.dumps({'title':item+' deleting success','text':item+' '+dom['name']+' will be deleted','icon':'success','type':'info'}), 200, {'ContentType':'application/json'}
                            else:
                                return json.dumps({'title':item+' deleting error','text':item+' '+dom['name']+' can\'t be deleted. Something went wrong!','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
                            # ~ else:
                                # ~ return json.dumps({'title':item+' deleting error','text':item+' '+dom['name']+' can\'t be deleted while not Stopped or Failed','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
                        else:
                            if dom['status'] in ['Stopped','Failed']:
                                if app.isardapi.update_table_value(table, data['pk'], data['name'], data['value']):
                                    return json.dumps({'title':item+' deleting success','text':item+' '+dom['name']+' will be deleted','icon':'success','type':'info'}), 200, {'ContentType':'application/json'}
                                else:
                                    return json.dumps({'title':item+' deleting error','text':item+' '+dom['name']+' can\'t be deleted. Something went wrong!','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
                            else:
                                return json.dumps({'title':item+' deleting error','text':item+' '+dom['name']+' can\'t be deleted while not Stopped or Failed','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
                    if data['value']=='Starting':
                        if dom['status'] in ['Stopped','Failed']:
                            exceeded = quotas.check('NewConcurrent',current_user.id)
                            if exceeded != False:
                                return json.dumps({'title':'Quota exceeded','text':item+' '+dom['name']+' can\'t be started. '+exceeded,'icon':'warning','type':'warning'}), 500, {'ContentType':'application/json'}

                            self.auto_interface_set(user,data['pk'],remote_addr)
                            if 'ephimeral' in dom.keys():
                                try:
                                    trigger=list(r.table('scheduler_jobs').filter({'action':'check_ephimeral_status'}).run(db.conn))[0]
                                    ci=trigger['next_run_time']
                                    i=1
                                    t=time.time()
                                    while ci < t+int(dom['ephimeral']['minutes'])*60:
                                        ci=trigger['next_run_time']+int(trigger['minute'])*60*i
                                        i=i+1
                                    dom['ephimeral']['finish']=trigger['next_run_time']+int(trigger['minute'])*60*(i-1)
                                    r.table(table).get(data['pk']).update({'ephimeral': dom['ephimeral']}).run(db.conn)
                                except Exception as e:
                                    r.table(table).get(data['pk']).replace(r.row.without('ephimeral')).run(db.conn)
                                    log.error('Exception in ephimeral time range set: '+str(e))
                            if app.isardapi.update_table_value(table, data['pk'], data['name'], data['value']):
                                return json.dumps({'title':False,'text':item+' '+dom['name']+' will be started','icon':'success','type':'info'}), 200, {'ContentType':'application/json'}
                            else:
                                return json.dumps({'title':item+' starting error','text':item+' '+dom['name']+' can\'t be started. Something went wrong!','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
                        else:
                            return json.dumps({'title':item+' starting error','text':item+' '+dom['name']+' can\'t be started while not Stopped or Failed','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
                return json.dumps({'title':'Method not allowed','text':'That action != allowed!','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}
            except Exception as e:
                log.error('Error updating status for '+dom['name']+': '+str(e))
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                log.error(exc_type, fname, exc_tb.tb_lineno)                
                return json.dumps({'title':item+' starting error','text':item+' '+dom['name']+' can\'t be started now','icon':'warning','type':'error'}), 500, {'ContentType':'application/json'}

    def auto_interface_set(self,user,id, remote_addr):
        with app.app_context():
            dict=r.table('domains').get(id).pluck("create_dict").run(db.conn)['create_dict']
            if dict['hardware']['interfaces'][0]=='default':
                return self.update_domain_network(user,id,remote_addr=remote_addr)
            else:
                return self.update_domain_network(user,id,interface_id=dict['hardware']['interfaces'][0])
        
    def update_domain_network(self,user,id,interface_id=False,remote_addr=False):
        try:
            if interface_id:
                with app.app_context():
                    iface=r.table('interfaces').get(interface_id).run(db.conn)
                    dict=r.table('domains').get(id).pluck("create_dict").run(db.conn)['create_dict']
                    dict["hardware"]["interfaces"]=[iface['id']]
                    return self.check(r.table('domains').get(id).update({"create_dict":dict}).run(db.conn),'replaced')
            elif remote_addr:
                # Automatic interface selection
                allowed_ifaces=self.get_alloweds(user,'interfaces',pluck=['id','net'])
                for iface in allowed_ifaces:
                    if IPAddress(remote_addr) in IPNetwork(iface['net']):
                        dict=r.table('domains').get(id).pluck("create_dict").run(db.conn)['create_dict']
                        dict["hardware"]["interfaces"]=[iface['id']]
                        return self.check(r.table('domains').get(id).update({"create_dict":dict}).run(db.conn),'replaced')
            return True
        except Exception as e:
            log.error('Error updating domain '+id+' network interface.\n'+str(e))
        return False
            
    def update_table_value(self, table, id, field, value):
        with app.app_context():
            return self.check(r.table(table).get(id).update({field: value}).run(db.conn),'replaced')


  

    '''
        MEDIA
    '''  

    def get_media_installs(self):
        with app.app_context():
            data=r.table('virt_install').run(db.conn)
            return self.f.table_values_bstrap(data)
    
    '''     
    STATUS
    '''
    def get_domain_last_messages(self, id):
        with app.app_context():
            return r.table('domains_status').get_all(id, index='name').order_by(r.desc('when')).pluck('when',{'status':['state','state_reason']}).limit(10).run(db.conn)

    def get_domain_last_events(self, id):
        with app.app_context():
            return r.table('hypervisors_events').get_all(id, index='domain').order_by(r.desc('when')).limit(10).run(db.conn)

    '''
    USER
    '''
    def get_user(self, user):
        with app.app_context():
            user=self.f.flatten_dict(r.table('users').get(user).run(db.conn))
            user['password']=''
        return user
                
    def get_user_domains(self, user, filterdict=False):
        if not filterdict: filterdict={'kind': 'desktop'}
        with app.app_context():
            domains=list(r.table('domains').get_all(user, index='user').filter(filterdict).without('xml','history_domain','allowed').run(db.conn))
        return domains

    def get_domain(self, id, human_size=False, flatten=True):
        #~ Should verify something???
        with app.app_context():
            domain = r.table('domains').get(id).without('xml','history_domain','progress').run(db.conn)
        try:
            if flatten:
                domain=self.f.flatten_dict(domain)
                if human_size:
                    domain['hardware-memory']=self.human_size(domain['hardware-memory'] * 1000)
                    if 'disks_info' in domain:
                        for i,dict in enumerate(domain['disks_info']):
                            for key in dict.keys():
                                if 'size' in key:
                                    domain['disks_info'][i][key]=self.human_size(domain['disks_info'][i][key])
            else:
                ''' This != used and will do nothing as we should implement a recursive function to look for all the nested 'size' fields '''
                if human_size:
                    domain['hardware']['memory']=self.human_size(domain['hardware']['memory'] * 1000)
                    if 'disks_info' in domain:
                        for i,dict in enumerate(domain['disks_info']):
                            for key in dict.keys():
                                if 'size' in key:
                                    domain['disks_info'][i][key]=self.human_size(domain['disks_info'][i][key])
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            log.error(exc_type, fname, exc_tb.tb_lineno)
        return domain   

    def get_domain_create_dict(self, id, human_size=False, flatten=True):
        #~ Should verify something???
        with app.app_context():
            hardware = r.table('domains').get(id).pluck({'create_dict':'hardware'}).run(db.conn)['create_dict']
        try:
            if flatten:
                hardware=self.f.flatten_dict(hardware)
                if human_size:
                    hardware['hardware-memory']=self.human_size(hardware['hardware-memory'] * 1000)
                    if 'disks_info' in hardware:
                        for i,dict in enumerate(hardware['disks_info']):
                            for key in dict.keys():
                                if 'size' in key:
                                    hardware['disks_info'][i][key]=self.human_size(hardware['disks_info'][i][key])
            else:
                ''' This != used and will do nothing as we should implement a recursive function to look for all the nested 'size' fields '''
                if human_size:
                    hardware['hardware']['memory']=self.human_size(hardware['hardware']['memory'] * 1000)
                    if 'disks_info' in hardware:
                        for i,dict in enumerate(hardware['disks_info']):
                            for key in dict.keys():
                                if 'size' in key:
                                    hardware['disks_info'][i][key]=self.human_size(hardware['disks_info'][i][key])
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            log.error(exc_type, fname, exc_tb.tb_lineno)
        return hardware  

    def get_domain_media(self,id):
        with app.app_context():
            domain_cd = r.table('domains').get(id).pluck({'create_dict':{'hardware'}}).run(db.conn)['create_dict']['hardware']
        media={'isos':[],'floppies':[]}
        if 'isos' in domain_cd and domain_cd['isos'] != []:
            for m in domain_cd['isos']:
                try:
                    iso=r.table('media').get(m['id']).pluck('id','name',{'progress':'total'}).run(db.conn)
                    #iso['size']=iso.pop('progress')['total']
                    media['isos'].append(iso)
                except:
                    ''' Media does not exist '''
                    None
        if 'floppies' in domain_cd and domain_cd['floppies'] != []:
            for m in domain_cd['floppies']:
                try:
                    fd=r.table('media').get(m['id']).pluck('id','name',{'progress':'total'}).run(db.conn)
                    #fd['size']=fd.pop('progress')['total']
                    media['floppies'].append(fd)
                except:
                    ''' Media does not exist '''
                    None
        return media

    def get_domain_media_list(self,id):
        with app.app_context():
            domain_cd = r.table('domains').get(id).pluck({'create_dict':{'hardware'}}).run(db.conn)['create_dict']['hardware']
        media=[]
        if 'isos' in domain_cd and domain_cd['isos'] != []:
            for m in domain_cd['isos']:
                try:
                    iso=r.table('media').get(m['id']).pluck('id','name',{'progress':'total'}).merge({'kind':'iso'}).run(db.conn)
                    iso['size']=iso.pop('progress')['total']
                    media.append(iso)
                except:
                    ''' Media does not exist '''
                    None
        if 'floppies' in domain_cd and domain_cd['floppies'] != []:
            for m in domain_cd['floppies']:
                try:
                    fd=r.table('media').get(m['id']).pluck('id','name',{'progress':'total'}).merge({'kind':'fd'}).run(db.conn)
                    fd['size']=fd.pop('progress')['total']
                    media.append(fd)
                except:
                    ''' Media does not exist '''
                    None
        return media                        

    def get_category(self,category):
        with app.app_context():
            try:
                return r.table('categories').get(category).pluck('id','name','description').run(db.conn)
            except:
                return False




    def get_user_templates(self, user):
        with app.app_context():
            dom = list(r.table('domains').get_all(user, index='user').filter(r.row['kind'].match('template')).without('viewer','xml','history_domain').run(db.conn))
            for d in dom:
                d['kind']=self.get_template_kind(user,d)
            return dom #self.f.table_values_bstrap(dom)

    def get_template_kind(self,user,d):
        if d['allowed']['roles'] == False and d['allowed']['categories'] == False and d['allowed']['groups'] == False:
            if (d['allowed']['users'] and user in d['allowed']['users']) or d['allowed']['users'] == False:    
                return 'Private'
        return 'Shared' 
                        

    def template_kind_toggle(self,user,id):
        with app.app_context():
            dom=r.table('domains').get(id).run(db.conn)
            allowed=dom['allowed']
            if not allowed['roles'] and not allowed['categories'] and not allowed['groups']:
                if (allowed['users'] and user in allowed['users']) or allowed['users'] == False:
                    allowed={'roles':[],'categories':[],'groups':[],'users':[]}
                    kind='public_template'
                    return self.check(r.table('domains').get(id).update({'allowed':allowed,'kind':kind}).run(db.conn),'replaced')
            allowed={'roles':False,'categories':False,'groups':False,'users':[user]}
            kind='user_template'
            return self.check(r.table('domains').get(id).update({'allowed':allowed,'kind':kind}).run(db.conn),'replaced')

    def get_alloweds(self, user, table, pluck=[], order=False):
        with app.app_context():
            ud=r.table('users').get(user).run(db.conn)
            delete_allowed_key=False
            if not 'allowed' in pluck: 
                pluck.append('allowed')
                delete_allowed_key=True
            allowed_data={}
            if table == 'domains':
                if order:
                    data=r.table('domains').get_all('public_template','user_template', index='kind').order_by(order).group('category').pluck({'id','name','allowed'}).run(db.conn)
                else:
                    data=r.table('domains').get_all('public_template','user_template', index='kind').group('category').pluck({'id','name','allowed'}).run(db.conn)
                for group in data:
                    allowed_data[group]=[]
                    for d in data[group]:
                        # False doesn't check, [] means all allowed
                        # Role is the master and user the least. If allowed in roles,
                        #   won't check categories, groups, users
                        allowed=d['allowed']
                        if d['allowed']['roles'] != False:
                            if not d['allowed']['roles']:  # Len != 0
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                            if ud['role'] in d['allowed']['roles']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                        if d['allowed']['categories'] != False:
                            if not d['allowed']['categories']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                            if ud['category'] in d['allowed']['categories']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                        if d['allowed']['groups'] != False:
                            if not d['allowed']['groups']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                            if ud['group'] in d['allowed']['groups']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                        if d['allowed']['users'] != False:
                            if not d['allowed']['users']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                            if user in d['allowed']['users']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                tmp_data=allowed_data.copy()
                for k,v in tmp_data.items():
                    if not len(tmp_data[k]):
                        allowed_data.pop(k,None)
                return allowed_data
            else:
                if order:
                    data=r.table(table).order_by(order).pluck(pluck).run(db.conn)
                else:
                    data=r.table(table).pluck(pluck).run(db.conn)
            allowed_data=[]
            for d in data:
                # False doesn't check, [] means all allowed
                # Role is the master and user the least. If allowed in roles,
                #   won't check categories, groups, users
                allowed=d['allowed']
                if d['allowed']['roles'] != False:
                    if not d['allowed']['roles']:  # Len != 0
                        if delete_allowed_key: d.pop('allowed', None)
                        allowed_data.append(d)
                        continue
                    if ud['role'] in d['allowed']['roles']:
                        if delete_allowed_key: d.pop('allowed', None)
                        allowed_data.append(d)
                        continue
                if d['allowed']['categories'] != False:
                    if not d['allowed']['categories']:
                        if delete_allowed_key: d.pop('allowed', None)
                        allowed_data.append(d)
                        continue
                    if ud['category'] in d['allowed']['categories']:
                        if delete_allowed_key: d.pop('allowed', None)
                        allowed_data.append(d)
                        continue
                if d['allowed']['groups'] != False:
                    if not d['allowed']['groups']:
                        if delete_allowed_key: d.pop('allowed', None)
                        allowed_data.append(d)
                        continue
                    if ud['group'] in d['allowed']['groups']:
                        if delete_allowed_key: d.pop('allowed', None)
                        allowed_data.append(d)
                        continue
                if d['allowed']['users'] != False:
                    if not d['allowed']['users']:
                        if delete_allowed_key: d.pop('allowed', None)
                        allowed_data.append(d)
                        continue
                    if user in d['allowed']['users']:
                        if delete_allowed_key: d.pop('allowed', None)
                        allowed_data.append(d)
            return allowed_data

    def get_alloweds_select2(self,allowed):
        for k,v in allowed.items():
            if v != False and len(v):
                with app.app_context():
                    """ allowed[k]=list(r.table(k).get_all(r.args(v), index='id').pluck('id','name').map(
                                                lambda doc: doc.merge({'text': doc['name']}).without('name')).run(db.conn)) """
                    allowed[k]=list(r.table(k).get_all(r.args(v), index='id').pluck('id','name','parent_category').run(db.conn))                                                
        return allowed
        
    def get_alloweds_domains(self, user, filter_type, custom_filter, pluck=[]):
        with app.app_context():
            ud=r.table('users').get(user).run(db.conn)
            delete_allowed_key=False
            if not 'allowed' in pluck: 
                pluck.append('allowed')
                delete_allowed_key=True
            allowed_data={}
            if filter_type=='base':
                #~ data=r.table('domains').get_all('base', index='kind').order_by('name').group('category').pluck({'id','name','allowed'}).run(db.conn)
                 data = r.table('domains').get_all('base', index='kind').filter(lambda d: d['allowed']['roles'] is not False or d['allowed']['groups'] is not False or d['allowed']['categories'] is not False).order_by('name').group('category').pluck({'id','name','allowed'}).run(db.conn)
            if filter_type=='user_template':
                ## This templates aren't shared, are user privated
                ## We can just return this.
                return r.table('domains').get_all(user, index='user').filter(r.row['kind'].match("template")).filter({'allowed':{'roles':False,'categories':False,'groups':False}}).order_by('name').group('category').pluck({'id','name','allowed'}).run(db.conn)
            if filter_type=='public_template':
                ## We should avoid the ones that have false in all allowed fields:
                ## Ex: This should be avoided as are user_templates not public:
                ##       {'allowed':{'roles':False,'categories':False,'groups':False}}
                data = r.table('domains').filter(r.row['kind'].match("template")).filter(custom_filter).filter(lambda d: d['allowed']['roles'] is not False or d['allowed']['groups'] is not False or d['allowed']['categories'] is not False).order_by('name').group('category').pluck({'id','name','allowed'}).run(db.conn)
            ## If we continue down here, data will be filtered by alloweds matching user role, domain, group and user
            #~ Generic get all: data=r.table('domains').get_all('public_template','user_template', index='kind').order_by('name').group('category').pluck({'id','name','allowed'}).run(db.conn)
            for group in data:
                    allowed_data[group]=[]
                    for d in data[group]:
                        # False doesn't check, [] means all allowed
                        # Role is the master and user the least. If allowed in roles,
                        #   won't check categories, groups, users
                        #~ allowed=d['allowed']
                        if d['allowed']['roles'] != False:
                            if not d['allowed']['roles']:  # Len != 0
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                            if ud['role'] in d['allowed']['roles']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                        if d['allowed']['categories'] != False:
                            if not d['allowed']['categories']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                            if ud['category'] in d['allowed']['categories']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                        if d['allowed']['groups'] != False:
                            if not d['allowed']['groups']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                            if ud['group'] in d['allowed']['groups']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                        if d['allowed']['users'] != False:
                            if not d['allowed']['users']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                            if user in d['allowed']['users']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
            tmp_data=allowed_data.copy()
            for k,v in tmp_data.items():
                if not len(tmp_data[k]):
                    allowed_data.pop(k,None)
            return allowed_data



    def get_all_alloweds_domains(self, user):
        with app.app_context():
            ud=r.table('users').get(user).run(db.conn)
            data1 = r.table('domains').get_all('base', index='kind').order_by('name').pluck({'id','name','allowed','kind','group','icon','user','category''description','status'}).run(db.conn)
            data2 = r.table('domains').filter(r.row['kind'].match("template")).order_by('name').pluck({'id','name','allowed','kind','group','icon','category','user','description','status'}).run(db.conn)
            data = data1+data2
            alloweds=[]
            for d in data:
                d['username']=r.table('users').get(d['user']).pluck('name').run(db.conn)['name']
                if ud['role']=='admin': 
                    alloweds.append(d)
                    continue
                if d['user']==ud['id']:
                    alloweds.append(d)
                    continue
                if d['allowed']['roles'] != False:
                    if len(d['allowed']['roles'])==0:
                        alloweds.append(d)
                        continue
                    else:
                        if ud['role'] in d['allowed']['roles']:
                            alloweds.append(d)
                            continue
                if d['allowed']['categories'] != False:
                    if len(d['allowed']['categories'])==0:
                        alloweds.append(d)
                        continue
                    else:
                        if ud['category'] in d['allowed']['categories']:
                            alloweds.append(d)
                            continue
                if d['allowed']['groups'] != False:
                    if len(d['allowed']['groups'])==0:
                        alloweds.append(d)
                        continue
                    else:
                        if ud['group'] in d['allowed']['groups']:
                            alloweds.append(d)
                            continue
                if d['allowed']['users'] != False:
                    if len(d['allowed']['users'])==0:
                        alloweds.append(d)
                        continue
                    else:
                        if ud['id'] in d['allowed']['users']:
                            alloweds.append(d)
                            continue   
            return alloweds

    def get_all_alloweds_table(self, table, user, pluck='default'):
        if pluck == 'default':
            pluck=['id','name','allowed','kind','icon','description']
        if pluck != False:
            if 'user' not in pluck: pluck.append('user')
            if 'allowed' not in pluck: pluck.append('allowed')            
        with app.app_context():
            ud=r.table('users').get(user).run(db.conn)
            delete_allowed_key=False
            if pluck != False:
                data1 = r.table(table).get_all(user, index='user').order_by('name').pluck(pluck).run(db.conn)
                data2 = r.table(table).filter(lambda d: d['allowed']['roles'] is not False or d['allowed']['groups'] is not False or d['allowed']['categories'] is not False or d['allowed']['users'] is not False).order_by('name').pluck(pluck).run(db.conn)
            else:
                data1 = r.table(table).get_all(user, index='user').order_by('name').run(db.conn)
                data2 = r.table(table).filter(lambda d: d['allowed']['roles'] is not False or d['allowed']['groups'] is not False or d['allowed']['categories'] is not False or d['allowed']['users'] is not False).order_by('name').run(db.conn)
            data=data1+data2
            data = [i for n, i in enumerate(data) if i not in data[n + 1:]]
            allowed_data=[]
            for d in data:
                        d['username']=r.table('users').get(d['user']).pluck('name').run(db.conn)['name']
                        if d['user']==user:
                            allowed_data.append(d)
                            continue
                        # False doesn't check, [] means all allowed
                        # Role is the master and user the least. If allowed in roles,
                        #   won't check categories, groups, users
                        #~ allowed=d['allowed']
                        if d['allowed']['roles'] != False:
                            if not d['allowed']['roles']:  # Len != 0
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                            if ud['role'] in d['allowed']['roles']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                        if d['allowed']['categories'] != False:
                            if not d['allowed']['categories']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                            if ud['category'] in d['allowed']['categories']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                        if d['allowed']['groups'] != False:
                            if not d['allowed']['groups']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                            if ud['group'] in d['allowed']['groups']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                        if d['allowed']['users'] != False:
                            if not d['allowed']['users']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                            if user in d['allowed']['users']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
            return allowed_data

    def get_all_table_allowed_term(self, table, kind, field, value, user, pluck='default'):
        if pluck == 'default':
            pluck=['id','name','allowed','kind','icon','user','description']
        if pluck != False:
            if 'user' not in pluck: pluck.append('user')
            if 'allowed' not in pluck: pluck.append('allowed')
        with app.app_context():
            ud=r.table('users').get(user).run(db.conn)
            delete_allowed_key=False
            if pluck != False:
                data = r.table(table).get_all(kind, index='kind').filter(lambda d: d['user'] is user or d['allowed']['roles'] is not False or d['allowed']['groups'] is not False or d['allowed']['categories'] is not False or d['allowed']['users'] is not False).order_by('name').pluck(pluck).run(db.conn)
            else:
                data = r.table(table).get_all(kind, index='kind').filter(lambda d: d['user']==user or d['allowed']['roles'] is not False or d['allowed']['groups'] is not False or d['allowed']['categories'] is not False or d['allowed']['users'] is not False).order_by('name').run(db.conn)
            allowed_data=[]
            for d in data:
                        d['username']=r.table('users').get(d['user']).pluck('name').run(db.conn)['name']
                        if d['user']==user:
                            allowed_data.append(d)
                            continue
                        # False doesn't check, [] means all allowed
                        # Role is the master and user the least. If allowed in roles,
                        #   won't check categories, groups, users
                        #~ allowed=d['allowed']
                        if d['allowed']['roles'] != False:
                            if not d['allowed']['roles']:  # Len != 0
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                            if ud['role'] in d['allowed']['roles']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                        if d['allowed']['categories'] != False:
                            if not d['allowed']['categories']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                            if ud['category'] in d['allowed']['categories']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                        if d['allowed']['groups'] != False:
                            if not d['allowed']['groups']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                            if ud['group'] in d['allowed']['groups']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                        if d['allowed']['users'] != False:
                            if not d['allowed']['users']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
                                continue
                            if user in d['allowed']['users']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data.append(d)
            return allowed_data
            
        
    def get_distinc_field(self, user, field, filter_type, pluck=[]):
        '''
        TODO: This is not ordering, probably because of dict keys
        '''
        #~ with app.app_context():
            #~ return r.table('domains').group(field).filter(filterDict).order_by(field).pluck(field).distinct().run(db.conn)
        with app.app_context():
            ud=r.table('users').get(user).run(db.conn)
            delete_allowed_key=False
            if not 'allowed' in pluck: 
                pluck.append('allowed')
                delete_allowed_key=True
            allowed_data={}
            ## Base != going to happen
            #~ if filter_type=='base':
                 #~ data = r.table('domains').get_all('base', index='kind').filter(lambda d: d['allowed']['roles'] != False or d['allowed']['groups'] != False or d['allowed']['categories'] != False).order_by('name').group('category').pluck({'id','name','allowed'}).run(db.conn)
            if filter_type=='user_template':
                ## This templates aren't shared, are user privated
                ## We can just return this.
                return r.table('domains').get_all(user, index='user').filter(r.row['kind'].match("template")).filter({'allowed':{'roles':False,'categories':False,'groups':False}}).order_by('name').group(field).pluck({'id','name','allowed'}).run(db.conn)
            if filter_type=='public_template':
                ## We should avoid the ones that have false in all allowed fields:
                ## Ex: This should be avoided as are user_templates not public:
                ##       {'allowed':{'roles':False,'categories':False,'groups':False}}
                data = r.table('domains').filter(r.row['kind'].match("template")).filter(lambda d: d['allowed']['roles'] is not False or d['allowed']['groups'] is not False or d['allowed']['categories'] is not False).order_by('name').group(field).pluck({'id','name','allowed'}).run(db.conn)
            ## If we continue down here, data will be filtered by alloweds matching user role, domain, group and user
            #~ Generic get all: data=r.table('domains').get_all('public_template','user_template', index='kind').order_by('name').group('category').pluck({'id','name','allowed'}).run(db.conn)
            for group in data:
                    allowed_data[group]=[]
                    for d in data[group]:
                        # False doesn't check, [] means all allowed
                        # Role is the master and user the least. If allowed in roles,
                        #   won't check categories, groups, users
                        allowed=d['allowed']
                        if d['allowed']['roles'] != False:
                            if not d['allowed']['roles']:  # Len != 0
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                            if ud['role'] in d['allowed']['roles']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                        if d['allowed']['categories'] != False:
                            if not d['allowed']['categories']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                            if ud['category'] in d['allowed']['categories']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                        if d['allowed']['groups'] != False:
                            if not d['allowed']['groups']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                            if ud['group'] in d['allowed']['groups']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                        if d['allowed']['users'] != False:
                            if not d['allowed']['users']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
                                continue
                            if user in d['allowed']['users']:
                                if delete_allowed_key: d.pop('allowed', None)
                                allowed_data[group].append(d)
            tmp_data=allowed_data.copy()
            for k,v in tmp_data.items():
                if not len(tmp_data[k]):
                    allowed_data.pop(k,None)
            return allowed_data
        
    def user_relative_media_path(self, user, filename):
        with app.app_context():
            userObj=r.table('users').get(user).pluck('id','category','group','provider','username','uid').run(db.conn)
        parsed_name = self.parse_string(filename)
        if not parsed_name: return False
        id = '_'+user+'-'+parsed_name
        #~ Missing check if id already exists
        dir_disk, disk_filename = self.get_disk_path(userObj, filename)
        return {'id':id,
                'name':filename,
                'path':dir_disk+'/'+filename,
                'user':user,
                'username': userObj['username'],
                'category':userObj['category'],
                'group':userObj['group'],}



        
    def new_tmpl_from_domain(self, from_id, form_data, user_id):
        """ exceeded = quotas.check('NewTemplate',user_id)
        if exceeded != False:
            return exceeded """

        parsed_name = self.parse_string(form_data['name'])
        template_id = '_' + user_id + '-' + parsed_name

        with app.app_context():
            # Checking if template exists:
            if r.table('domains').get(template_id).run(db.conn) != None: return 'Template name already exists.'

            # Lets construct new template_dict data
            desktop=r.table('domains').get(from_id).without('disks_info','history_domain','xml_to_start').run(db.conn)
            user=r.table('users').get(user_id).pluck('id','category','group','provider','username','uid').run(db.conn)


        parent_disk=desktop['hardware']['disks'][0]['file']

        dir_disk, disk_filename = self.get_disk_path(user, parsed_name)
        form_data['create_dict']['hardware']['disks']=[{'file':dir_disk+'/'+disk_filename,
                                            'parent':parent_disk}]

        hardware=self.parse_media_info(form_data['create_dict'])['hardware']
        
        template_dict={'id': template_id,
                  'name': form_data['name'],
                  'description': form_data['description'],
                  'kind': form_data['kind'],
                  'user': user['id'],
                  'username': user['username'],
                  'status': 'CreatingTemplate',
                  'detail': None,
                  'category': user['category'],
                  'group': user['group'],
                  'xml': desktop['xml'], #### In desktop creation is 
                  'icon': desktop['icon'],
                  'server': desktop['server'],
                  'os': desktop['os'],
                  'options': desktop['options'],
                  'create_dict': {'hardware':hardware, 
                                    'origin': from_id}, 
                  'hypervisors_pools': form_data['hypervisors_pools'],
                  'parents': desktop['parents'] if 'parents' in desktop.keys() else [],
                  'allowed': form_data['allowed']}

        with app.app_context():
            return self.check(r.table('domains').get(from_id).update({"create_dict": {"template_dict": template_dict}, "status": "CreatingTemplate"}).run(db.conn),'replaced')

    def new_domains_auto_user(self,user,auto_templates):
        with app.app_context():
            usr_dsk=r.table('domains').get_all(user, index='user').filter({'kind':'desktop'}).run(db.conn)
            usr_dsk_list=[d['id'] for d in usr_dsk]
        for t in auto_templates['desktops']:
            if '_'+user+'-'+t.split("-",2)[2] in usr_dsk_list: continue
            with app.app_context():
                tmpl=r.table('domains').get(t).run(db.conn)    
                tmpl['create_dict']['template']=tmpl['id']
                tmpl['create_dict']['name']=tmpl['name']
                tmpl['create_dict']['description']=tmpl['description']
                tmpl['create_dict']['hypervisors_pools']=tmpl['hypervisors_pools']
                        
            self.new_domain_from_tmpl(user, tmpl['create_dict'])

    def new_domain_from_tmpl(self, user, create_dict):
        exceeded = quotas.check('NewDesktop',user)
        if exceeded != False:
            return exceeded
        with app.app_context():
            userObj=r.table('users').get(user).pluck('id','category','group','provider','username','uid').run(db.conn)
            ephimeral_cat=r.table('categories').get(userObj['category']).pluck('ephimeral').run(db.conn)
            ephimeral_group=r.table('groups').get(userObj['group']).pluck('ephimeral').run(db.conn)
        ephimeral = ephimeral_group if 'ephimeral' in ephimeral_group.keys() else  ephimeral_cat
        
        dom=app.isardapi.get_domain(create_dict['template'])
            
        parent_disk=dom['hardware-disks'][0]['file']

        qos_id=create_dict.pop('qos_id') if 'qos_id' in create_dict.keys() else False
        parsed_name = self.parse_string(create_dict['name'])
        dir_disk, disk_filename = self.get_disk_path(userObj, parsed_name)
        create_dict['hardware']['disks']=[{'file':dir_disk+'/'+disk_filename,
                                            'parent':parent_disk,
                                            'qos_id': qos_id}]

        create_dict=self.parse_media_info(create_dict)
        new_domain={'id': '_'+user+'-'+parsed_name,
                  'name': create_dict['name'],
                  'description': create_dict['description'],
                  'kind': 'desktop',
                  'user': userObj['id'],
                  'username': userObj['username'],
                  'status': 'Creating',
                  'detail': None,
                  'category': userObj['category'],
                  'group': userObj['group'],
                  'xml': None,
                  'icon': dom['icon'],
                  'server': dom['server'],
                  'os': dom['os'],
                  'options': {'viewers':{'spice':{'fullscreen':True}}},
                  'create_dict': {'hardware':create_dict['hardware'], 
                                    'origin': create_dict['template']}, 
                  'hypervisors_pools': create_dict['hypervisors_pools'],
                  'allowed': {'roles': False,
                              'categories': False,
                              'groups': False,
                              'users': False}}
        if 'ephimeral' in ephimeral.keys():
            new_domain['ephimeral']=ephimeral['ephimeral']
        with app.app_context():
            if r.table('domains').get(new_domain['id']).run(db.conn) == None:
                return self.check(r.table('domains').insert(new_domain).run(db.conn),'inserted')
            else:
                return 'Domain name already exists.'

    def update_domain(self, create_dict):
        id=create_dict['id']
        create_dict.pop('id',None)
        #~ description=create_dict['description']
        #~ create_dict.pop('description',None)
        
        if 'diskbus' in create_dict['create_dict']['hardware']:
            new_create_dict=r.table('domains').get(id).pluck('create_dict').run(db.conn)
            if len(new_create_dict['create_dict']['hardware']['disks']):
                new_create_dict['create_dict']['hardware']['disks'][0]['bus']=create_dict['create_dict']['hardware']['diskbus']
                create_dict['create_dict']['hardware']['disks']=new_create_dict['create_dict']['hardware']['disks']
            create_dict['create_dict']['hardware'].pop('diskbus',None)

        if 'qos_id' in create_dict['create_dict']['hardware']:
            create_dict['create_dict']['hardware']['disks'][0]['qos_id']=create_dict['create_dict']['hardware']['qos_id']
            create_dict['create_dict']['hardware'].pop('qos_id',None)

        create_dict['create_dict']=self.parse_media_info(create_dict['create_dict'])
              
        create_dict['status']='Updating'
        return self.check(r.table('domains').get(id).update(create_dict).run(db.conn),'replaced')
        #~ return update_table_value('domains',id,{'create_dict':'hardware'},create_dict['hardware'])

    def parse_media_info(self, create_dict):
        medias=['isos','floppies','storage']
        for m in medias:
            if m in create_dict['hardware']:
                newlist=[]
                for item in create_dict['hardware'][m]:
                    with app.app_context():
                        newlist.append(r.table('media').get(item['id']).pluck('id','name','description').run(db.conn))
                create_dict['hardware'][m]=newlist
        return create_dict

    def update_user_password(self,id,passwd):
        pw=Password()
        self.update_table_value('users',current_user.id,'password',pw.encrypt(passwd))
        return True
    
    """ def user_hardware_allowed(self, user_id)
        return quota.user_hardware_allowed(user_id) """

    '''
    HELPERS
    '''

    #~ GENERIC
    def check(self,dict,action):
        '''
        These are the actions:
        {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
        '''
        if dict[action]: 
            return True
        if not dict['errors']: return True
        return False
        
    def parse_string(self, txt):
        import re, unicodedata, locale
        if type(txt) != str:
            txt = txt.decode('utf-8')
        #locale.setlocale(locale.LC_ALL, 'ca_ES')
        prog = re.compile("[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$")
        if not prog.match(txt):
            return False
        else:
            # ~ Replace accents
            txt = ''.join((c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn'))
            return txt.replace(" ", "_")

    """ def toCamel(self,phrase):
        split = re.split('_| ',phrase)
        return self.parse_string(split[0]).lower() + self.parse_string(''.join(x.capitalize() for x in split[1:])) """

    def toCamel(self, phrase):
        split = re.split('_| ',phrase)
        if len(split) > 1:
            return self.parse_string(split[0]).lower() + self.parse_string(''.join(x.capitalize() for x in split[1:] if x != ''))
        else:
            return self.parse_string(split[0]).lower()


    def get_disk_path(self, user, parsed_name):
        with app.app_context():
            group_uid = r.table('groups').get(user['group']).run(db.conn)['uid']

        dir_path = user['category']+'/'+group_uid+'/'+user['provider']+'/'+user['uid']+'-'+user['username']
        filename = parsed_name + '.qcow2'
        return dir_path,filename
        
    def human_size(self, size_bytes):
        """
        format a size in bytes into a 'human' file size, e.g. bytes, KB, MB, GB, TB, PB
        Note that bytes/KB will be reported in whole numbers but MB and above will have greater precision
        e.g. 1 byte, 43 bytes, 443 KB, 4.3 MB, 4.43 GB, etc
        """
        if size_bytes == 1:
            # because I really hate unnecessary plurals
            return "1 byte"

        suffixes_table = [('bytes',0),('KB',0),('MB',0),('GB',2),('TB',2), ('PB',2)]

        num = float(size_bytes)
        for suffix, precision in suffixes_table:
            if num < 1024.0:
                break
            num /= 1024.0

        if precision == 0:
            formatted_size = "%d" % num
        else:
            formatted_size = str(round(num, ndigits=precision))

        return "%s %s" % (formatted_size, suffix)

    def flatten_dict(self,d):
        def items():
            for key, value in list(d.items()):
                if isinstance(value, dict):
                    for subkey, subvalue in list(self.flatten_dict(value).items()):
                        yield key + "-" + subkey, subvalue
                else:
                    yield key, value
        return dict(items())

    def unflatten_dict(dictionary):
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

