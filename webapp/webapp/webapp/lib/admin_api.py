# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
import time
from webapp import app
from werkzeug import secure_filename

from datetime import datetime, timedelta
from string import digits, ascii_lowercase
import random

import requests, socket
import tarfile,pickle,os

import pem
from OpenSSL import crypto

from contextlib import closing
    
import rethinkdb as r

from ..lib.log import * 
import traceback 

from .flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from ..auth.authentication import Password
import secrets

from collections import defaultdict

from .ds import DS
ds = DS()


class isardAdmin():
    def __init__(self):
        self.f=flatten()


    def check(self,dict,action):
        #~ These are the actions:
        #~ {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
        if dict[action] or dict['unchanged']: 
            return True
        if not dict['errors']: return True
        return False

        
    def check_socket(self, host, port):
        try:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                if sock.connect_ex((host, port)) == 0:
                    return True
                else:
                    return False
        except:
            return False
                    
    '''
    ADMIN API
    '''
    def delete_table_key(self,table,key):
        with app.app_context():
            return self.check(r.table(table).get(key).delete().run(db.conn),'deleted')

    def multiple_action(self, table, action, ids):
        with app.app_context():
            if action == 'toggle':
                domains_stopped=self.multiple_check_field(table,'status','Stopped',ids)
                domains_started=self.multiple_check_field(table,'status','Started',ids)
                res_stopped=r.table(table).get_all(r.args(domains_stopped)).update({'status':'Starting'}).run(db.conn)
                res_started=r.table(table).get_all(r.args(domains_started)).update({'status':'Stopping'}).run(db.conn)
                return True
            if action == 'delete':
                domains_deleting=self.multiple_check_field(table,'status','Deleting',ids)
                res=r.table(table).get_all(r.args(domains_deleting)).delete().run(db.conn) 
                                
                domains_stopped=self.multiple_check_field(table,'status','Stopped',ids)
                res=r.table(table).get_all(r.args(domains_stopped)).update({'status':'Deleting'}).run(db.conn)
                domains_disabled=self.multiple_check_field(table,'status','Disabled',ids)
                res=r.table(table).get_all(r.args(domains_disabled)).update({'status':'Deleting'}).run(db.conn)                
                domains_failed=self.multiple_check_field(table,'status','Failed',ids)
                res=r.table(table).get_all(r.args(domains_failed)).update({'status':'Deleting'}).run(db.conn) 
                domains_creating=self.multiple_check_field(table,'status','Creating',ids)
                res=r.table(table).get_all(r.args(domains_creating)).update({'status':'Deleting'}).run(db.conn)                                              
                domains_creatingdisk=self.multiple_check_field(table,'status','CreatingDisk',ids)
                res=r.table(table).get_all(r.args(domains_creatingdisk)).update({'status':'Deleting'}).run(db.conn) 
                domains_creatingstarting=self.multiple_check_field(table,'status','CreatingAndStarting',ids)
                res=r.table(table).get_all(r.args(domains_creatingstarting)).update({'status':'Deleting'}).run(db.conn) 
                return True
            if action == 'force_failed':
                res_deleted=r.table(table).get_all(r.args(ids)).update({'status':'Failed'}).run(db.conn)
                return True
            if action == 'force_stopped':
                res_deleted=r.table(table).get_all(r.args(ids)).update({'status':'Stopped'}).run(db.conn)
                return True
            if action == "stop_noviewer":
                domains_tostop=self.multiple_check_field(table,'status','Started',ids)
                res=r.table(table).get_all(r.args(domains_tostop)).filter(~r.row.has_fields({'viewer':'client_since'})).update({'status':'Stopping'}).run(db.conn)
                return True
                
    def multiple_check_field(self, table, field, value, ids):
        with app.app_context():
            return [d['id'] for d in list(r.table(table).get_all(r.args(ids)).filter({field:value}).pluck('id').run(db.conn))]

    def get_group(self,id):
        with app.app_context():
            group = r.table('groups').get(id).run(db.conn)  
        if group == None: return {}
        return group

    def get_admin_table(self, table, pluck=False, id=False, order=False, flatten=True):
        with app.app_context():
            if id and not pluck:
                data=r.table(table).get(id).run(db.conn)
                return self.f.flatten_dict(data) if flatten else data
            if pluck and not id:
                if order:
                    data=r.table(table).order_by(order).pluck(pluck).run(db.conn)
                    return self.f.table_values_bstrap(data) if flatten else list(data)
                else:
                    data=r.table(table).pluck(pluck).run(db.conn)
                    return self.f.table_values_bstrap(data) if flatten else list(data)
            if pluck and id:
                data=r.table(table).get(id).pluck(pluck).run(db.conn)
                return self.f.flatten_dict(data) if flatten else data
            if order:
                data=r.table(table).order_by(order).run(db.conn)
                return self.f.table_values_bstrap(data) if flatten else list(data)
            else:
                data=r.table(table).run(db.conn)
                return self.f.table_values_bstrap(data) if flatten else list(data)

    def get_admin_table_term(self, table, field, value, kind=False, pluck=False):
        with app.app_context():
            if kind:
                if pluck:
                    return self.f.table_values_bstrap(r.table(table).get_all(kind, index='kind').filter(lambda doc: doc[field].match('(?i)'+value)).pluck(pluck).run(db.conn))
                else:
                    return self.f.table_values_bstrap(r.table(table).get_all(kind, index='kind').filter(lambda doc: doc[field].match('(?i)'+value)).run(db.conn))
            else:
                if pluck:
                    return self.f.table_values_bstrap(r.table(table).filter(lambda doc: doc[field].match('(?i)'+value)).pluck(pluck).run(db.conn))
                else:
                    return self.f.table_values_bstrap(r.table(table).filter(lambda doc: doc[field].match('(?i)'+value)).run(db.conn))
                
    def insert_table_dict(self, table, dict):
        with app.app_context():
            return self.check(r.table(table).insert(dict).run(db.conn), 'inserted')

    def insert_or_update_table_dict(self, table, dict):
        with app.app_context():
            return r.table(table).insert(dict, conflict='update').run(db.conn)
                                        
    def update_table_dict(self, table, id, dict):
        with app.app_context():
            return self.check(r.table(table).get(id).update(dict).run(db.conn), 'replaced')

    def update_keyvalue(self,table,key, oldvalue, newvalue):
        with app.app_context():
            data = r.table(table).filter({key:oldvalue}).run(db.conn)
            if data != None:
                return self,check(r.table(table).filter({key:oldvalue}).update({key:newvalue}).run(db.conn), 'replaced')
    '''
    USERS
    '''
    def user_add(self,user):
        p = Password()
        usr = { 'provider': 'local',
                'uid': user['username'],
                'active': True,
                'accessed': time.time(),
                'password': p.encrypt(user['password'])}
        del user['password']
        user={**usr, **user}
        
        if user['quota'] != False:
            for k,v in user['quota'].items():
                user['quota'][k]=int(v)
            for k,v in user['quota'].items():
                user['quota'][k]=int(v)     

        '''Pre defined desktops'''
        with app.app_context():
            desktops_cat=r.table('categories').get(user['category']).pluck('auto').run(db.conn)
            desktops_group=r.table('groups').get(user['group']).pluck('auto','parent_category').run(db.conn)
        desktops = desktops_group if 'auto' in desktops_group.keys() else desktops_cat        

        if 'auto' in desktops.keys():
            user['auto']=desktops['auto']        

        user['id']='local-'+user['category']+'-'+user['uid']+'-'+user['username']
        return self.check(r.table('users').insert(user).run(db.conn),'inserted')

    def users_add(self,users):
        p = Password()
        final_users=[]
        for user in users:
            
            usr = { 'provider': 'local',
                    'uid': user['username'],
                    'active': True,
                    'accessed': time.time(),
                    'password': p.encrypt(user['password'].rstrip())}
            del user['password']
            user={**usr, **user}

            if user['quota'] != False:
                for k,v in user['quota'].items():
                    user['quota'][k]=int(v)
                for k,v in user['quota'].items():
                    user['quota'][k]=int(v)     

            '''Pre defined desktops'''
            with app.app_context():
                desktops_cat=r.table('categories').get(user['category']).pluck('auto').run(db.conn)
                desktops_group=r.table('groups').get(user['group']).pluck('auto','parent_category').run(db.conn)
            desktops = desktops_group if 'auto' in desktops_group.keys() else desktops_cat        

            if 'auto' in desktops.keys():
                user['auto']=desktops['auto'] 

            user['id']='local-'+user['category']+'-'+user['uid']+'-'+user['username']

            final_users.append(user)          
        return self.check(r.table('users').insert(final_users).run(db.conn),'inserted')

    def user_edit(self,user):
        if user['quota'] != False:
            for k,v in user['quota'].items():
                user['quota'][k]=int(v)
            for k,v in user['quota'].items():
                user['quota'][k]=int(v)
        return self.check(r.table('users').update(user).run(db.conn),'replaced')

    def user_passwd(self,user):
        p = Password()
        usr = {'password': p.encrypt(user['password'])}
        return self.check(r.table('users').get(user['id']).update(usr).run(db.conn),'replaced')
        
    def user_toggle_active(self,id):
        with app.app_context():
            is_active = not r.table('users').get(id).pluck('active').run(db.conn)['active'] 
            if is_active:
                r.table('domains').get_all(id, index='user').filter({'kind':'desktop','status':'Disabled'}).update({'status':'Stopped'}).run(db.conn)
            else:
                r.table('domains').get_all(id, index='user').filter({'kind':'desktop'}).update({'status':'Disabled'}).pluck('id').run(db.conn)
            return self.check(r.table('users').get(id).update({'active':is_active}).run(db.conn),'replaced')

                    
    def get_admin_user(self):
        with app.app_context():
            ## ALERT: Should remove password (password='')
            return self.f.table_values_bstrap(r.table('users').run(db.conn))

    def get_admin_users_domains(self):
        with app.app_context():
            return self.f.table_values_bstrap(
                r.table("users").merge(lambda user:
                    {
                        "desktops": r.table("domains").get_all(user['id'], index='user').filter({'kind': 'desktop'}).count(),
                        "public_template": r.table("domains").get_all(user['id'], index='user').filter({'kind': 'public_template'}).count(),
                        "user_template": r.table("domains").get_all(user['id'], index='user').filter({'kind': 'user_template'}).count(),
                        "base": r.table("domains").get_all(user['id'], index='user').filter({'kind': 'base'}).count()
                    }
                ).run(db.conn))


    def items_delete(self,list):
        errors=[]
        for i in list:
            if i['kind'] in ['desktop','template']:
                try:
                    ds.delete_desktop(i['id'],i['status']) 
                except:
                    errors.append(i)
        return errors if len(errors) else False

    def template_delete_list(self,id):
        with app.app_context():
            dom_id=r.table('domains').get(id).pluck('id','name','kind','user','status','parents').run(db.conn)
            doms = list(r.table('domains').pluck('id','name','kind','user','status','parents').filter(lambda derivates: derivates['parents'].contains(id)).run(db.conn))
            return [dom_id]+doms

    def template_delete(self,id):
        try:
            for d in self.template_delete_list(id):
                ds.delete_desktop(d['id'],d['status'])
            return True
        except Exception as e:
            log.error('Error deleting template '+id+'\n'+str(e))
            return False

    def user_delete_checks(self,user_id):
        with app.app_context():
            user_desktops = list(r.table("domains").get_all(user_id, index='user').filter({'kind': 'desktop'}).pluck('id','name','kind','user','status','parents').run(db.conn))
            user_templates = list(r.table("domains").get_all(r.args(['base','public_template','user_template']),index='kind').filter({'user':user_id}).pluck('id','name','kind','user','status','parents').run(db.conn))
            derivated = []
            for ut in user_templates:
                id = ut['id']
                derivated = derivated + list(r.table('domains').pluck('id','name','kind','user','status','parents').filter(lambda derivates: derivates['parents'].contains(id)).run(db.conn))
                #templates = [t for t in derivated if t['kind'] != "desktop"]
                #desktops = [d for d in derivated if d['kind'] == "desktop"]
        domains = user_desktops+user_templates+derivated
        return [i for n, i in enumerate(domains) if i not in domains[n + 1:]] 
    
    def user_delete(self,user_id):
        with app.app_context():
            try:
                for d in self.user_delete_checks(user_id):
                    ds.delete_desktop(d['id'],d['status'])
                r.table('users').get(user_id).delete().run(db.conn)
                return True
            except Exception as e:
                log.error('Error deleting user and related items. '+user_id+'\n'+str(e))
                return False

    def category_delete_checks(self,category_id):
        with app.app_context():
            category = r.table('categories').get(category_id).pluck('id','name').run(db.conn)
            if category == None:
                return []
            else:
                category.update({"kind":"category","user":category['id']})
                categories=[category]
            groups = list(r.table('groups').filter({'parent_category':category_id}).pluck('id','name').run(db.conn))
            for g in groups:
                g.update({"kind":"group","user":g['id']})
            users = list(r.table('users').get_all(category_id, index='category').pluck('id','name').run(db.conn))
            for u in users:
                u.update({"kind":"user","user":u['id']})

            category_desktops = list(r.table("domains").get_all(category_id, index='category').filter({'kind': 'desktop'}).pluck('id','name','kind','user','status','parents').run(db.conn))
            category_templates = list(r.table("domains").get_all(r.args(['base','public_template','user_template']),index='kind').filter({'category':category_id}).pluck('id','name','kind','user','status','parents').run(db.conn))
            derivated = []
            for ut in category_templates:
                id = ut['id']
                derivated = derivated + list(r.table('domains').pluck('id','name','kind','user','status','parents').filter(lambda derivates: derivates['parents'].contains(id)).run(db.conn))
                #templates = [t for t in derivated if t['kind'] != "desktop"]
                #desktops = [d for d in derivated if d['kind'] == "desktop"]
        domains = categories+groups+users+category_desktops+category_templates+derivated
        return [i for n, i in enumerate(domains) if i not in domains[n + 1:]] 
    
    def category_delete(self,category_id):
        with app.app_context():
            try:
                for d in self.category_delete_checks(category_id):
                    if d['kind'] == 'user':
                        r.table('users').get(d['id']).delete().run(db.conn)
                    elif d['kind'] == 'group':
                        r.table('groups').get(d['id']).delete().run(db.conn)
                    elif d['kind'] == 'category':
                        r.table('categories').get(d['id']).delete().run(db.conn)                        
                    else:
                        ds.delete_desktop(d['id'],d['status'])
                return True
            except Exception as e:
                print(traceback.format_exc())
                log.error('Error deleting category  '+category_id+' and related items.\n'+str(traceback.format_exc()))
                return False

    def group_delete_checks(self,group_id):
        with app.app_context():
            try:
                group = r.table('groups').get(group_id).pluck('id','name').run(db.conn)
            except:
                return []
            else:
                group.update({"kind":"group","user":group['id']})
                groups=[group]
            users = list(r.table('users').get_all(group_id, index='group').pluck('id','name').run(db.conn))
            for u in users:
                u.update({"kind":"user","user":u['id']})

            group_desktops = list(r.table("domains").get_all(group_id, index='group').filter({'kind': 'desktop'}).pluck('id','name','kind','user','status','parents').run(db.conn))
            group_templates = list(r.table("domains").get_all(r.args(['base','public_template','user_template']),index='kind').filter({'group':group_id}).pluck('id','name','kind','user','status','parents').run(db.conn))
            derivated = []
            for gt in group_templates:
                id = gt['id']
                derivated = derivated + list(r.table('domains').pluck('id','name','kind','user','status','parents').filter(lambda derivates: derivates['parents'].contains(id)).run(db.conn))
                #templates = [t for t in derivated if t['kind'] != "desktop"]
                #desktops = [d for d in derivated if d['kind'] == "desktop"]
        domains = groups+users+group_desktops+group_templates+derivated
        return [i for n, i in enumerate(domains) if i not in domains[n + 1:]] 
    
    def group_delete(self,group_id):
        with app.app_context():
            try:
                for d in self.group_delete_checks(group_id):
                    if d['kind'] == 'user':
                        r.table('users').get(d['id']).delete().run(db.conn)
                    elif d['kind'] == 'group':
                        r.table('groups').get(d['id']).delete().run(db.conn)                        
                    else:
                        ds.delete_desktop(d['id'],d['status'])
                return True
            except Exception as e:
                log.error('Error deleting group and related items.'+group_id+'\n'+str(e))
                return False

    def ___user_delete_checks(self,user_id):
        with app.app_context():
            # User desktops can be deleted, ok?
            user_desktops = list(r.table("domains").get_all(user_id, index='user').filter({'kind': 'desktop'}).pluck('id','name','user',{'create_dict':{'origin'}}).run(db.conn))
            
            # User templates... depending. Are they owned by himself only? Or they have other user derivates??
            user_templates = list(r.table("domains").get_all(r.args(['base','public_template','user_template']),index='kind').filter({'user':user_id}).pluck('id','name','user',{'create_dict':{'origin'}}).run(db.conn))
            risky_templates=[]
            others_domains=0
            for t in user_templates:
                all_template_derivates = self.domain_derivates_count(t['id'])
                usr_template_derivates = self.domain_derivates_count(t['id'],user_id)
                if all_template_derivates != usr_template_derivates:
                    # We've got a problem. There are templates owned by other users. We can't delete this user!
                    t['other_users_derivates']=all_template_derivates - usr_template_derivates
                    risky_templates.append(t)
                    others_domains+=all_template_derivates - usr_template_derivates
        return {'desktops':user_desktops,
                'templates':user_templates,
                'risky_templates':risky_templates,
                'others_domains':others_domains}

    def rcg_quota_update(self,quota):
        id=quota['id']
        quota.pop('id',None)
        table=quota['table']
        quota.pop('table',None)   
        if 'propagate' in quota.keys():
            propagate=quota['propagate'] 
            quota.pop('propagate',None)
        else:
            propagate=False

        try:
            ## Check that no group limits exceed parent category limits
            if table == 'groups' and 'limits' in quota.keys():
                with app.app_context():
                    group = r.table('groups').get(id).run(db.conn)
                    category = r.table('categories').get(group['parent_category']).run(db.conn)
                if category['limits'] != False:
                    for k,v in category['limits'].items():
                        if v < quota['limits'][k]: quota['limits'][k]=v
            ## Ok, update quota now
            with app.app_context():
                r.table(table).get(id).update(quota).run(db.conn)
        except:
            return False
        
        ## If downupdate is set then will populate:
        ##      quota: category -> groups -> users
        ##     limits: category -> groups
        ## (Users don't have limits implicit as limits are for all users in cat/group)
        if propagate == True:
            if table == 'categories':
                with app.app_context():
                    ## Update quotas&limits to all groups from this category
                    r.table('groups').get_all(id, index='parent_category').update(quota).run(db.conn)
                ## Also, if quota is in keys, populate quota to all users in those categories.
                ## If only limits is in keys then finish here as users don't have limits
                if 'quota' in quota.keys():
                    with app.app_context():
                        groups = r.table('groups').get_all(id, index='parent_category').pluck('id').run(db.conn)
                        groups = [g['id'] for g in groups]
                        r.table('users').get_all(r.args(groups), index='group').update({'quota':quota['quota']}).run(db.conn)
            ## If table is groups then only populate quota (not limits) to users
            if table == 'groups':
                if 'quota' in quota.keys():
                    with app.app_context():
                        r.table('users').get_all(id, index='group').update({'quota':quota['quota']}).run(db.conn)                

        return True


    def category_group_update(self,dict):
        table=dict['table']
        dict.pop('table',None)  
        id=dict['id']
        dict.pop('id',None)
        if 'frontend' not in dict.keys():
            r.table(table).get(id).replace(r.row.without('frontend')).run(db.conn)        
        if 'auto' not in dict.keys():
            r.table(table).get(id).replace(r.row.without('auto')).run(db.conn)
        if 'ephimeral' not in dict.keys():
            r.table(table).get(id).replace(r.row.without('ephimeral')).run(db.conn)            
        r.table(table).get(id).update(dict).run(db.conn)
        return True

    def rcg_add(self,dict,current_user):
        if 'id' in dict.keys():
            return self.category_group_update(dict)
        table=dict['table']
        dict.pop('table',None)
        dict['id']=app.isardapi.parse_string(dict['name']).lower()
        dict['limits'] = False
        dict['quota'] = False
        if table == "categories":    
            groupdict=dict.copy()
            groupdict['id']=dict['id']+'-main'
            groupdict['uid']='Main' #dict['id']
            groupdict['parent_category'] = dict['id']
            groupdict['name']='Main'
            groupdict['description']='['+dict['name']+'] main group'
            groupdict['enrollment'] = {'manager':False, 'advanced':False, 'user':False}
            r.table('groups').insert(groupdict).run(db.conn)
            return self.check(r.table(table).insert(dict).run(db.conn),'inserted')
        elif table == "groups":
            groupdict=dict.copy()
            if 'parent_category' not in groupdict.keys():
                groupdict['parent_category'] = current_user.category
            groupdict['uid']=app.isardapi.parse_string(dict['id'])
            groupdict['id']=groupdict['parent_category']+'-'+dict['id']              
            category_name=r.table('categories').get(groupdict['parent_category']).run(db.conn)['name']
            #groupdict['name']=category_name+' '+dict['name']
            groupdict['description']='['+category_name+'] '+dict['description']
            groupdict['enrollment'] = {'manager':False, 'advanced':False, 'user':False}
            return self.check(r.table('groups').insert(groupdict).run(db.conn),'inserted')            
        else:
            return self.check(r.table(table).insert(dict).run(db.conn),'inserted')

    '''
    DOMAINS
    '''
                                
    #~ def get_admin_domains(self,kind=False):
        #~ with app.app_context():
            #~ if not kind:
                #~ return self.f.table_values_bstrap(r.table('domains').without('xml','hardware','create_dict').run(db.conn))
            #~ else:
                 #~ return self.f.table_values_bstrap(r.table('domains').get_all(kind,index='kind').without('xml','hardware','create_dict').run(db.conn))

    def get_admin_domains_with_derivates(self,id=False,kind=False):
        with app.app_context():
            if 'template' in kind:
                if not id:
                    return list(r.table("domains").get_all(r.args(['public_template','user_template']),index='kind').without('xml','history_domain').merge(lambda domain:
                        {
                            "derivates": r.table('domains').filter(lambda derivates: derivates['parents'].contains(domain['id'])).count()
                            # ~ "derivates": r.table('domains').filter({'create_dict':{'origin':domain['id']}}).count()
                        }
                    ).run(db.conn))
                if id:
                    return list(r.table("domains").get(id).without('xml','history_domain').merge(lambda domain:
                        {
                            "derivates": r.table('domains').filter(lambda derivates: derivates['parents'].contains(domain['id'])).count()
                            # ~ "derivates": r.table('domains').filter({'create_dict':{'origin':domain['id']}}).count()
                        }
                    ).run(db.conn))
            elif kind == 'base':
                if not id:
                    return list(r.table("domains").get_all(kind,index='kind').without('xml','history_domain').merge(lambda domain:
                        {
                            "derivates": r.table('domains').filter(lambda derivates: derivates['parents'].contains(domain['id'])).count()
                            # ~ "derivates": r.table('domains').filter({'create_dict':{'origin':domain['id']}}).count()
                        }
                    ).run(db.conn))
                if id:
                    return list(r.table("domains").get(id).without('xml','history_domain').merge(lambda domain:
                        {
                            "derivates": r.table('domains').filter(lambda derivates: derivates['parents'].contains(domain['id'])).count()
                        }
                    ).run(db.conn))                
            else:
               return list(r.table("domains").get_all(kind,index='kind').without('xml').merge(lambda domain:
                    {
                        "accessed": domain['history_domain'][0]['when'].default(0)
                    }
                ).run(db.conn))

    def is_template_removable(self,tmpl_id,user_id):
        all_template_derivates = self.domain_derivates_count(tmpl_id)
        usr_template_derivates = self.domain_derivates_count(tmpl_id,user_id)
        if all_template_derivates != usr_template_derivates:
            # Thre are templates/isard-admin/desktops not owned by the user
            return False 
        else: 
            return True


    def domain_derivates_count(self,id=False,username=False):
        with app.app_context():
            if username == False:
                domains= [ {'id':d['id'],'origin':(d['create_dict']['origin'] if 'create_dict' in d and 'origin' in d['create_dict'] else None)}
                            for d in list(r.table('domains').pluck('id',{'create_dict':{'origin'}}).run(db.conn)) ] 
            else:
                domains= [ {'id':d['id'],'origin':(d['create_dict']['origin'] if 'create_dict' in d and 'origin' in d['create_dict'] else None)}
                            for d in list(r.table('domains').get_all(username, index='user').pluck('id','user',{'create_dict':{'origin'}}).run(db.conn)) ] 

            return self.domain_recursive_count(id,domains)-1

    def domains_update(self, create_dict):
        ids=create_dict['ids']
        create_dict.pop('ids',None)

        for id in ids:
            create_dict['status']='Updating'
            self.check(r.table('domains').get(id).update(create_dict).run(db.conn),'replaced')
        return self.check(r.table('domains').get(id).update(create_dict).run(db.conn),'replaced')

    def domain_recursive_count(self,id,domains):

        count = 1
        doms= [d for d in domains if d['origin']==id]
        for dom in doms:
            count+= self.domain_recursive_count(dom['id'],domains)
        return count

    def domains_stop(self,hyp_id=False,without_viewer=True):
        with app.app_context():
            try:
                if without_viewer:
                    if hyp_id == False:
                        return r.table('domains').get_all('Started',index='status').filter({'viewer':{'client_since':False}}).update({'status':'Stopping'}).run(db.conn)['replaced']
                    else:
                        return r.table('domains').get_all('Started',index='status').filter({'hyp_started':hyp_id,'viewer':{'client_since':False}}).update({'status':'Stopping'}).run(db.conn)['replaced']
                else:
                    if hyp_id == False:
                        return r.table('domains').get_all('Started',index='status').update({'status':'Stopping'}).run(db.conn)['replaced']
                    else:
                        return r.table('domains').get_all('Started',index='status').filter({'hyp_started':hyp_id}).update({'status':'Stopping'}).run(db.conn)['replaced']
                    
            except:
                return False

    def domains_mdelete(self,dict):
        '''We got domains again just to be sure they have not changed during the modal'''
        newdict = self.template_delete_list(dict['id'])
        newids = [d['id'] for d in newdict]
        if set(dict['ids']) == set(newids):
            '''This is the only needed if it works StoppingAndDeleting'''
            # ~ r.table('domains').get_all(r.args(newids)).update({'status':'StoppingAndDeleting'}).run(db.conn) 
            
            maintenance=[d['id'] for d in newdict if d['status'] != 'Started']
            res=r.table('domains').get_all(r.args(maintenance)).update({'status':'Maintenance'}).run(db.conn)            
            
            # Stopping domains
            started=[d['id'] for d in newdict if d['status'] == 'Started']
            res=r.table('domains').get_all(r.args(started)).update({'status':'Stopping'}).run(db.conn)
            if res['replaced'] > 0:
                # Wait a bit for domains to be stopped...
                for i in range(0,5):
                    time.sleep(.5)
                    if r.table('domains').get_all(r.args(started)).filter({'status':'Stopping'}).pluck('status').run(db.conn) == None:
                        r.table('domains').get_all(r.args(started)).filter({'status':'Stopped'}).update({'status':'Maintenance'}).run(db.conn) 
                        break
                    else:
                        r.table('domains').get_all(r.args(started)).filter({'status':'Stopped'}).update({'status':'Maintenance'}).run(db.conn) 
                    
                    
            # Deleting
            # ~ tmpls = [d for d in newdict if d['kind'] != 'desktop']
            # ~ desktops = [d for d in newdict if d['kind'] == 'desktop']
            
            # ~ r.table('domains').get_all(r.args(desktops)).update({'status':'Deleting'}).run(db.conn) 
            # ~ time.sleep(1)
            # ~ r.table('domains').get_all(r.args(tmpls)).update({'status':'Deleting'}).run(db.conn) 
            r.table('domains').get_all(r.args(newids)).update({'status':'Stopped'}).run(db.conn) 
            r.table('domains').get_all(r.args(newids)).update({'status':'Deleting'}).run(db.conn) 
            return True
        return False
        
                
    def get_admin_templates(self,term):
        with app.app_context():
            data1 = r.table('domains').get_all('base', index='kind').filter(r.row['name'].match(term)).order_by('name').pluck({'id','name','kind','group','icon','user','description'}).run(db.conn)
            data2 = r.table('domains').filter(r.row['kind'].match("template")).filter(r.row['name'].match(term))    .order_by('name').pluck({'id','name','kind','group','icon','user','description'}).run(db.conn)
        return data1+data2
            
    def update_forcedhyp(self,dom_id,forced_hyp):
        try:
            with app.app_context():
                r.table('domains').get(dom_id).update({'forced_hyp':forced_hyp}).run(db.conn)
            return True
        except:
            None
        return False
    '''
    HYPERVISORS
    '''
    def hypervisors_get(self, id=False):
        with app.app_context():
            if id:
                flat_dict_list = self.f.flatten_dict(r.table("hypervisors").get(id).merge(lambda hyp:
                                    {
                                        "started_domains": r.table('domains').get_all('Started', index='status').filter({'hyp_started':hyp['id']}).count()
                                    }
                                ).run(db.conn))
            else:
                flat_dict_list = self.f.table_values_bstrap(r.table("hypervisors").merge(lambda hyp:
                                {
                                    "started_domains": r.table('domains').get_all('Started', index='status').filter({'hyp_started':hyp['id']}).count()
                                }
                            ).run(db.conn))
        return flat_dict_list

    def hypervisors_pools_get(self, flat=True):
        with app.app_context():
            if flat:
                return self.f.table_values_bstrap(r.table('hypervisors_pools').run(db.conn))
            else:
                return list(r.table('hypervisors_pools').run(db.conn))
                            
    def hypervisor_toggle_enabled(self,id):
        with app.app_context():
            is_enabled = r.table('hypervisors').get(id).pluck('enabled').run(db.conn)['enabled']
            started_domains = r.table('domains').get_all('Started', index='status').filter({'hyp_started':id}).count()

            if started_domains==0 :            
                status=not is_enabled
                return self.check(r.table('hypervisors').get(id).update({'enabled':status}).run(db.conn),'replaced')
            
            else:
                return False
                
    def hypervisor_add(self,dict):
        with app.app_context():
            if dict['capabilities']['disk_operations']:
                id=dict['id']
                cap_disk=dict['capabilities']['disk_operations']
                cap_hyp=dict['capabilities']['hypervisor']
                for hp in dict['hypervisors_pools']:
                    paths=r.table('hypervisors_pools').get(hp).run(db.conn)['paths']
                    for p in paths:
                        path_list=[]
                        for i,path_data in enumerate(paths[p]):
                            if id not in path_data['disk_operations']:
                                path_data['disk_operations'].append(id)
                                paths[p][i]['disk_operations']=path_data['disk_operations']
                    r.table('hypervisors_pools').get(hp).update({'paths':paths,'enabled':False}).run(db.conn)
            return self.check(r.table('hypervisors').insert(dict).run(db.conn),'inserted')

    def hypervisor_pool_add(self,dict):
        with app.app_context():
            return self.check(r.table('hypervisors_pools').insert(dict).run(db.conn),'inserted')

    def hypervisor_edit(self,dict):
        with app.app_context():
            old_hyp=r.table('hypervisors').get(dict['id']).run(db.conn)
            if not (old_hyp['status']=='Offline' or old_hyp['status']=='Error'): return False
            if old_hyp['capabilities']['disk_operations'] and not dict['capabilities']['disk_operations']:
                # We should remove it from pool. It != going to be a disk op anymore!
                id=dict['id']
                for hp in dict['hypervisors_pools']:
                    paths=r.table('hypervisors_pools').get(hp).run(db.conn)['paths']
                    for p in paths:
                        path_list=[]
                        for i,path_data in enumerate(paths[p]):
                            if id in path_data['disk_operations']:
                                path_data['disk_operations'].remove(id)
                                paths[p][i]['disk_operations']=path_data['disk_operations']
                    r.table('hypervisors_pools').get(hp).update({'paths':paths}).run(db.conn)                
            
            
            if dict['capabilities']['disk_operations'] and not old_hyp['capabilities']['disk_operations']:
                # It was't a disk op, but now it will
                id=dict['id']
                for hp in dict['hypervisors_pools']:
                    paths=r.table('hypervisors_pools').get(hp).run(db.conn)['paths']
                    for p in paths:
                        path_list=[]
                        for i,path_data in enumerate(paths[p]):
                            if id not in path_data['disk_operations']:
                                path_data['disk_operations'].append(id)
                                paths[p][i]['disk_operations']=path_data['disk_operations']
                    r.table('hypervisors_pools').get(hp).update({'paths':paths,'enabled':False}).run(db.conn)
            return self.check(r.table('hypervisors').update(dict).run(db.conn),'replaced')


    def hypervisor_delete(self,id):
        with app.app_context():
            started_domains = r.table('domains').get_all('Started', index='status').filter({'hyp_started':id}).count()
            if started_domains==0:
                dict=r.table('hypervisors').get(id).run(db.conn)
                if dict['status']=='Deleting':
                    r.table('hypervisors_events').filter({'hyp_id':id}).delete().run(db.conn)
                    r.table('hypervisors_status').filter({'hyp_id':id}).delete().run(db.conn)
                    r.table('hypervisors_status_history').filter({'hyp_id':id}).delete().run(db.conn)
                    
                    if dict['capabilities']['disk_operations']:
                        # ~ id=dict['id']
                        cap_disk=dict['capabilities']['disk_operations']
                        cap_hyp=dict['capabilities']['hypervisor']
                        for hp in dict['hypervisors_pools']:
                            paths=r.table('hypervisors_pools').get(hp).run(db.conn)['paths']
                            for p in paths:
                                path_list=[]
                                for i,path_data in enumerate(paths[p]):
                                    if id in path_data['disk_operations']:
                                        path_data['disk_operations'].remove(id)
                                        paths[p][i]['disk_operations']=path_data['disk_operations']
                            r.table('hypervisors_pools').get(hp).update({'paths':paths}).run(db.conn)
                    return self.check(r.table('hypervisors').get(id).delete().run(db.conn),'deleted')
                else:
                    app.adminapi.update_table_dict('hypervisors',id,{'enabled':False,'status':'Deleting'})
                    return True
            else:
                return False
                

    def get_admin_config(self, id=None):
        with app.app_context():
            if id == None:
                return self.f.flatten_dict(r.table('config').get(1).run(db.conn))
            else:
                return self.f.flatten_dict(r.table('config').get(1).run(db.conn))
                


    '''
    MEDIA
    '''
    def media_add(self,user_id,partial_dict,filename=False):
        ## (Should be checked on socketio/url)
        """ exceeded = app.isardapi.check_quota_limits('NewIso',user_id)
        if exceeded != False:
            return exceeded """

        try:
            partial_dict['url-web']=partial_dict['url']
            del partial_dict['url']
            if filename == False:
                filename = partial_dict['url-web'].split('/')[-1]
            user_data=app.isardapi.user_relative_media_path( user_id, partial_dict['name'])
            partial_dict={**partial_dict, **user_data}
            missing_keys={  'accessed': time.time(),
                            'detail': 'Downloaded from website',
                            'icon': 'fa-circle-o' if partial_dict['kind']=='iso' else 'fa-floppy-o',
                            'progress': {
                                "received":  "0" ,
                                "received_percent": 0 ,
                                "speed_current":  "" ,
                                "speed_download_average":  "" ,
                                "speed_upload_average":  "" ,
                                "time_left":  "" ,
                                "time_spent":  "" ,
                                "time_total":  "" ,
                                "total":  "" ,
                                "total_percent": 0 ,
                                "xferd":  "0" ,
                                "xferd_percent":  "0"
                                },
                            'status': 'DownloadStarting',
                            'url-isard': False,
                            }
            dict={**partial_dict, **missing_keys}
            return self.insert_table_dict('media',dict)
        except Exception as e:
            log.error(str(e))
            log.error('Exception error on media add')
            return False
        return False

    def media_upload(self,username,handler,media):
        path='./uploads/'
        
        media['id']=handler.filename
        filename = secure_filename(handler.filename)
        handler.save(os.path.join(path+filename))

        id='_'+username+'-'+app.isardapi.parse_string(media['name'])
        name=media['name']
        try:
            user_data=app.isardapi.user_relative_media_path( username, filename)
            media={**media, **user_data}
            media['id']=id
            media['name']=name
            missing_keys={  'accessed': time.time(),
                            'detail': 'Uploaded from local',
                            'icon': 'fa-circle-o' if media['kind']=='iso' else 'fa-floppy-o',
                            'progress': {
                                "received":  "0" ,
                                "received_percent": 0 ,
                                "speed_current":  "" ,
                                "speed_download_average":  "" ,
                                "speed_upload_average":  "" ,
                                "time_left":  "" ,
                                "time_spent":  "" ,
                                "time_total":  "" ,
                                "total":  "" ,
                                "total_percent": 0 ,
                                "xferd":  "0" ,
                                "xferd_percent":  "0"
                                },
                            'status': 'DownloadStarting',
                            'url-isard': False,
                            }
            dict={**media, **missing_keys}
            return self.insert_table_dict('media',dict)
        except Exception as e:
            log.error(str(e))
            log.error('Exception error on media add')
            return False
        return False

    def media_delete_list(self,id):
        with app.app_context():
            return list(r.table('domains').filter( lambda dom: dom['create_dict']['hardware']['isos'].contains( lambda media: media['id'].eq(id))).pluck('id','name','kind','status', { "create_dict": { "hardware": {"isos"}}}).run(db.conn))

    def media_delete(self,id):
        ## Needs optimization by directly doing operation in nested array of dicts in reql
        domains=self.media_delete_list(id)
        # ~ domids=[d['id'] for d in domains]
        for dom in domains:
            domid=dom['id']
            if dom['status'] == 'Started': continue
            if dom['status'] != 'Stopped':
                r.table('domains').get(domid).update({'status':'Stopped'}).run(db.conn)
            dom['create_dict']['hardware']['isos'][:]= [iso for iso in dom['create_dict']['hardware']['isos'] if iso.get('id') != id]
            dom.pop('id',None)
            dom.pop('name',None)
            dom.pop('kind',None)
            dom['status']='Updating'
            with app.app_context():
                r.table('domains').get(domid).update(dom).run(db.conn)
        return True
        
        # ~ domids=[d['id'] for d in self.media_delete_list(id)]
        # ~ with app.app_context():
            # ~ r.table('domains').get_all(r.args(domids)).update(
                # ~ lambda dom: { "create_dict": { "hardware": {"isos": dom['create_dict']['hardware']['isos'].ne(id) }}}
            # ~ ).run(db.conn)
        # ~ return True
            
            
    # ~ def media_domains_used():
        # ~ return list(r.table('domains').filter(
                # ~ lambda dom: 
                    # ~ (r.args(dom['create_dict']['hardware']['isos'])['id'].eq(id) | r.args(dom['create_dict']['hardware']['floppies'])['id'].eq(id))
                # ~ ).run(conn))
        # ~ return list(r.table("domains").filter({'create_dict':{'hardware':{'isos':id}}).pluck('id').run(db.conn))                    

    # ~ def delete_media(self,id):
        # ~ with app.app_context():
            # ~ return r.table('domains').filter(
                # ~ lambda dom: 
                        # ~ (r.args(dom['create_dict']['hardware']['isos'])['id'].eq(id) | r.args(dom['create_dict']['hardware']['floppies'])['id'].eq(id))
                    # ~ ).run(conn))
            
            # ~ hardware - isos [ {path}, ... ]
            # ~ return self.f.table_values_bstrap(data)  

       
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
           

    '''
    BACKUP & RESTORE
    '''
    def backup_db(self):
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
        skip_tables=['backups','domains_status','hypervisors_events','hypervisors_status','domains_status_history','hypervisors_status_history','disk_operations']
        isard_db={}
        with app.app_context():
            r.table('backups').get(id).update({'status':'Loading tables'}).run(db.conn)
            for table in r.table_list().run(db.conn):
                if table not in skip_tables:
                    isard_db[table]=list(r.table(table).run(db.conn))
                    dict['data'][table]=r.table(table).info().run(db.conn)
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

    def recreate_table(self,tbl_data):
        if not r.table_list().contains(tbl_data['name']).run(db.conn):
            log.info("Restoring table {}".format(k))
            r.table_create(tbl_data['name'], primary_key=tbl_data['primary_key']).run(db.conn)
            for idx in tbl_data['indexes']:
                r.table(tbl_data['name']).index_create(idx).run(db.conn)
                r.table(tbl_data['name']).index_wait(idx).run(db.conn)
                log.info('Created index: {}'.format(idx))
                
    def restore_db(self,id):
        with app.app_context():
            dict=r.table('backups').get(id).run(db.conn)
            r.table('backups').get(id).update({'status':'Uncompressing backup'}).run(db.conn)
        path=dict['path']
        with tarfile.open(path+id+'.tar.gz', "r:gz") as tar:
            tar.extractall(path)
            tar.close()
        with app.app_context():
            r.table('backups').get(id).update({'status':'Loading data..'}).run(db.conn)
        with open(path+id+'.rethink', 'rb') as tbl_data_file:
            tbl_data = pickle.load(tbl_data_file)
        with open(path+id+'.json', 'rb') as isard_db_file:
            isard_db = pickle.load(isard_db_file)
        for k,v in isard_db.items():
            with app.app_context():
                try:
                    self.recreate_table(tbl_data[k])
                except Exception as e:
                    pass
                if not r.table_list().contains(k).run(db.conn):
                    log.error("Table {} not found, should have been created on IsardVDI startup.".format(k))
                    continue
                    #~ return False
                else:
                    log.info("Restoring table {}".format(k))
                    with app.app_context():
                        r.table('backups').get(id).update({'status':'Updating table: '+k}).run(db.conn)
                    # Avoid updating admin user!
                    if k == 'users': v[:] = [u for u in v if u.get('id') != 'admin']
                    log.info(r.table(k).insert(v, conflict='update').run(db.conn))
        with app.app_context():
            r.table('backups').get(id).update({'status':'Finished restoring'}).run(db.conn)
        try:
            os.remove(path+id+'.json')
            os.remove(path+id+'.rethink')
        except OSError as e:
            log.error(e)
            pass

    def download_backup(self,id):
        with app.app_context():
            dict=r.table('backups').get(id).run(db.conn)
        with open(dict['path']+dict['filename'], 'rb') as isard_db_file:
            return dict['path'],dict['filename'], isard_db_file.read()
            
    def info_backup_db(self,id):
        with app.app_context():
            dict=r.table('backups').get(id).run(db.conn)
            #~ r.table('backups').get(id).update({'status':'Uncompressing backup'}).run(db.conn)
        path=dict['path']
        with tarfile.open(path+id+'.tar.gz', "r:gz") as tar:
            tar.extractall(path)
            tar.close()
        #~ with app.app_context():
            #~ r.table('backups').get(id).update({'status':'Loading data..'}).run(db.conn)
        with open(path+id+'.rethink', 'rb') as tbl_data_file:
            tbl_data = pickle.load(tbl_data_file)
        with open(path+id+'.json', 'rb') as isard_db_file:
            isard_db = pickle.load(isard_db_file)
        i=0
        for sch in isard_db['scheduler_jobs']:
            isard_db['scheduler_jobs'][i].pop('job_state',None)
            i=i+1
        #~ i=0
        #~ for sch in isard_db['users']:
            #~ isard_db['users'][i].pop('password',None)
            #~ i=i+1            
        try:
            os.remove(path+id+'.json')
            os.remove(path+id+'.rethink')
        except OSError as e:
            log.error(e)
            pass
        return tbl_data,isard_db

    def check_new_values(self,table,new_data):
        backup=new_data
        dbb=list(r.table(table).run(db.conn))
        result=[]
        for b in backup:
            found=False
            for d in dbb:
                if d['id']==b['id']:
                    found=True
                    b['new_backup_data']=False
                    result.append(b)
                    break
            if not found: 
                b['new_backup_data']=True
                result.append(b)
        return result
    
    def upload_backup(self,handler):
        path='./backups/'
        id=handler.filename.split('.tar.gz')[0]
        filename = secure_filename(handler.filename)
        handler.save(os.path.join(path+filename))
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
                    
    

    '''
    VIRT-BUILDER VIRT-INSTALL
    '''

    def domain_from_virtbuilder(self, user, name, description, icon, create_dict, hyper_pools, disk_size):
        with app.app_context():
            userObj=r.table('users').get(user).pluck('id','category','group','provider','username','uid').run(db.conn)
            create_dict['install']['options']='' #r.table('domains_virt_install').get(create_dict['install']['id']).pluck('options').run(db.conn)['options']
        
        parsed_name = app.isardapi.parse_string(name)
        dir_disk, disk_filename = app.isardapi.get_disk_path(userObj, parsed_name)
        create_dict['hardware']['disks']=[{'file':dir_disk+'/'+disk_filename,
                                            'size':disk_size}]   # 15G as a format
        new_domain={'id': '_'+user+'-'+parsed_name,
                  'name': name,
                  'description': description,
                  'kind': 'desktop',
                  'user': userObj['id'],
                  'username': userObj['username'],
                  'status': 'CreatingFromBuilder',
                  'detail': None,
                  'category': userObj['category'],
                  'group': userObj['group'],
                  'xml': None,
                  'icon': icon,
                  'server': False,
                  'os': create_dict['builder']['id'],   #### Or name
                  'options': {'viewers':{'spice':{'fullscreen':True}}},
                  'create_dict': create_dict, 
                  'hypervisors_pools': hyper_pools,
                  'allowed': {'roles': False,
                              'categories': False,
                              'groups': False,
                              'users': False}}
        with app.app_context():
            return self.check(r.table('domains').insert(new_domain).run(db.conn),'inserted')

    def domain_from_media(self, user, name, description, icon, create_dict, hyper_pools, disk_size):
        with app.app_context():
            userObj=r.table('users').get(user).pluck('id','category','group','provider','username','uid').run(db.conn)
        
        parsed_name = app.isardapi.parse_string(name)
        dir_disk, disk_filename = app.isardapi.get_disk_path(userObj, parsed_name)
        create_dict['hardware']['disks']=[{'file':dir_disk+'/'+disk_filename,
                                            'size':disk_size}]   # 15G as a format
        media=r.table('media').get(create_dict['media']).run(db.conn)
        if media['kind']=='iso':
            create_dict['hardware']['isos']=[{'id': create_dict['media']}]
            create_dict['hardware']['floppies']=[]     
        if media['kind']=='floppy':
            create_dict['hardware']['isos']=[]
            create_dict['hardware']['floppies']=[{'id': create_dict['media']}]                                                                                           

        if 'add_virtio_iso' in create_dict:
            with app.app_context():
                iso_virtio_id=list(r.table('media').has_fields('default-virtio-iso').pluck('id').run(db.conn))
            if len(iso_virtio_id):
                create_dict['hardware']['isos'].append({'id': iso_virtio_id[0]['id']})
                create_dict.pop('add_virtio_iso',None)
            
            create_dict['hardware']['disks'].append({'file':'admin/isard-admin/admin/isard-admin/admin/virtio_testdisk.qcow2',
                                                'readonly':True,
                                                'type_path': 'media',
                                                'bus':'virtio'
                                                })   # 15G as a format    
            
        new_domain={'id': '_'+user+'-'+parsed_name,
                  'name': name,
                  'description': description,
                  'kind': 'desktop',
                  'user': userObj['id'],
                  'username': userObj['username'],
                  'status': 'CreatingDiskFromScratch',
                  'detail': None,
                  'category': userObj['category'],
                  'group': userObj['group'],
                  'xml': None,
                  'icon': icon,
                  'server': False,
                  'os': create_dict['create_from_virt_install_xml'],   #### Or name
                  'options': {'viewers':{'spice':{'fullscreen':False}}},
                  'create_dict': create_dict, 
                  'hypervisors_pools': hyper_pools,
                  'allowed': {'roles': False,
                              'categories': False,
                              'groups': False,
                              'users': False}}
        with app.app_context():
            return self.check(r.table('domains').insert(new_domain).run(db.conn),'inserted')


    '''
    JUMPERURL
    '''
    def get_jumperurl(self,id):
        with app.app_context():
            domain = r.table('domains').get(id).run(db.conn)  
        if domain == None: return {}
        if 'jumperurl' not in domain.keys(): return {'jumperurl':False}
        return {'jumperurl':domain['jumperurl']}

    def jumperurl_reset(self, id, disabled=False, length=128):
        if disabled==True:
            with app.app_context():
                r.table('domains').get(id).update({'jumperurl':False}).run(db.conn)
            return True
        
        code = False
        while code == False:
            code = secrets.token_urlsafe(length) 
            found=list(r.table('domains').filter({'jumperurl':code}).run(db.conn))
            if len(found) == 0:            
                with app.app_context():
                    r.table('domains').get(id).update({'jumperurl':code}).run(db.conn)                
                return code
        return False

    '''
    ENROLLMENT
    '''


    def enrollment_gen(self, length=6):
        chars = digits + ascii_lowercase
        dict = {}
        for key in ['manager','advanced','user']:
            code = False
            while code == False:
                code = "".join([random.choice(chars) for i in range(length)]) 
                if self.enrollment_code_check(code) == False:
                    dict[key]=code
                else:
                    code = False

        return dict  

    def enrollment_reset(self, id, role, disabled=False, length=6):
        if disabled==True:
            with app.app_context():
                r.table('groups').get(id).update({'enrollment':{role:False}}).run(db.conn)
            return True
        chars = digits + ascii_lowercase
        code = False
        while code == False:
            code = "".join([random.choice(chars) for i in range(length)]) 
            if self.enrollment_code_check(code) == False:
                with app.app_context():
                    r.table('groups').get(id).update({'enrollment':{role:code}}).run(db.conn)                
                return code
        return False



    def enrollment_code_check(self, code):
        with app.app_context():
            found=list(r.table('groups').filter({'enrollment':{'manager':code}}).run(db.conn))
            if len(found) > 0:
                category = found[0]['parent_category'] #found[0]['id'].split('_')[0]
                return {'code':code,'role':'manager', 'category':category, 'group':found[0]['id']}
            found=list(r.table('groups').filter({'enrollment':{'advanced':code}}).run(db.conn))
            if len(found) > 0:
                category = found[0]['parent_category'] #found[0]['id'].split('_')[0]
                return {'code':code,'role':'advanced', 'category':category, 'group':found[0]['id']}
            found=list(r.table('groups').filter({'enrollment':{'user':code}}).run(db.conn))
            if len(found) > 0:
                category = found[0]['parent_category'] #found[0]['id'].split('_')[0]
                return {'code':code,'role':'user', 'category':category, 'group':found[0]['id']}  
        return False              


'''
FLATTEN AND UNFLATTEN DICTS
'''        
class flatten(object):
    def __init__(self):
        None

    def table_header_bstrap(self, table, pluck=None, editable=False):
        columns=[]
        for key, value in list(self.flatten_table_keys(table,pluck).items()):
            if editable and key != 'id':
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
            if pluck != None:
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
