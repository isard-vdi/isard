#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import time
from api import app
from datetime import datetime, timedelta
import pprint

from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlTimeoutError

import logging as log

from .flask_rethink import RDB
db = RDB(app)
db.init_app(app)

from ..auth.authentication import *

from ..libv2.isardViewer import isardViewer
isardviewer = isardViewer()

from .apiv2_exc import *

from .helpers import _check, _parse_string, _parse_media_info, _disk_path

from .ds import DS 
ds = DS()

from .helpers import _check, _random_password

class ApiUsers():
    def __init__(self):
        self.au=auth()

    def Login(self,user_id,user_passwd):
        user=self.au._check(user_id,user_passwd)
        if user == False:
            raise UserLoginFailed

    def Exists(self,user_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) is None:
                raise UserNotFound

    def Create(self, provider, category_id, user_uid, user_username, role_id, group_id, password=False, photo='', email=''):
        # password=False generates a random password
        with app.app_context():
            id = provider+'-'+category_id+'-'+user_uid+'-'+user_username
            if r.table('users').get(id).run(db.conn) != None:
                raise UserExists

            if r.table('roles').get(role_id).run(db.conn) is None: raise RoleNotFound
            if r.table('categories').get(category_id).run(db.conn) is None: raise CategoryNotFound
            group = r.table('groups').get(group_id).run(db.conn)
            if group is None: raise GroupNotFound

            if password == False:
                password = _random_password()

            user = {'id': id,
                    'name': user_username,
                    'uid': user_uid,
                    'provider': provider,
                    'active': True,
                    'accessed': time.time(),
                    'username': user_username,
                    'password': bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                    'role': role_id,
                    'category': category_id,
                    'group': group_id,
                    'email': email,
                    'photo': photo,
                    'default_templates':[],
                    'quota': group['quota'],  # 10GB
                    }
            if not _check(r.table('users').insert(user).run(db.conn),'inserted'):
                raise NewUserNotInserted #, conflict='update').run(db.conn)
        return user['id']

    def Update(self, user_id, user_name, user_email='', user_photo=''):
        self.Exists(user_id)
        with app.app_context():
            if not _check(r.table('users').get(user_id).update({'name':user_name, 'email':user_email, 'photo':user_photo}).run(db.conn),'replaced'):
                raise UpdateFailed

    def Templates(self,user_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) == None:
                raise UserNotFound
        try:
            with app.app_context():
                ud=r.table('users').get(user_id).run(db.conn)
            if ud == None:
                raise UserNotFound
            with app.app_context():
                data1 = r.table('domains').get_all('base', index='kind').order_by('name').pluck({'id','name','allowed','kind','group','icon','user','description'}).run(db.conn)
                data2 = r.table('domains').filter(r.row['kind'].match("template")).order_by('name').pluck({'id','name','allowed','kind','group','icon','user','description'}).run(db.conn)
            data = data1+data2
            alloweds=[]
            for d in data:
                with app.app_context():
                    d['username']=r.table('users').get(d['user']).pluck('name').run(db.conn)['name']
                if ud['role']=='admin':
                    alloweds.append(d)
                    continue
                if d['user']==ud['id']:
                    alloweds.append(d)
                    continue
                if d['allowed']['roles'] is not False:
                    if len(d['allowed']['roles'])==0:
                        alloweds.append(d)
                        continue
                    else:
                        if ud['role'] in d['allowed']['roles']:
                            alloweds.append(d)
                            continue
                if d['allowed']['categories'] is not False:
                    if len(d['allowed']['categories'])==0:
                        alloweds.append(d)
                        continue
                    else:
                        if ud['category'] in d['allowed']['categories']:
                            alloweds.append(d)
                            continue
                if d['allowed']['groups'] is not False:
                    if len(d['allowed']['groups'])==0:
                        alloweds.append(d)
                        continue
                    else:
                        if ud['group'] in d['allowed']['groups']:
                            alloweds.append(d)
                            continue
                if d['allowed']['users'] is not False:
                    if len(d['allowed']['users'])==0:
                        alloweds.append(d)
                        continue
                    else:
                        if ud['id'] in d['allowed']['users']:
                            alloweds.append(d)
                            continue
            return alloweds
        except Exception as e:
            raise UserTemplatesError

    def Desktops(self,user_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) == None:
                raise UserNotFound
        try:
            with app.app_context():
                return list(r.table('domains').get_all(user_id, index='user').filter({'kind':'desktop'}).order_by('name').pluck({'id','name','icon','user','status','description'}).run(db.conn))

        except Exception as e:
            raise UserDesktopsError

    def Delete(self,user_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) is None:
                raise UserNotFound
        todelete = self._user_delete_checks(user_id)
        for d in todelete:
            try:
                ds.delete_desktop(d['id'],d['status'])
            except:
                raise
        #self._delete_non_persistent(user_id)
        if not _check(r.table('users').get(user_id).delete().run(db.conn),"deleted"):
            raise UserDeleteFailed

    def _user_delete_checks(self,user_id):
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

    def CodeSearch(self,code):
        with app.app_context():
            found=list(r.table('groups').filter({'enrollment':{'manager':code}}).run(db.conn))
            if len(found) > 0:
                category = found[0]['parent_category'] #found[0]['id'].split('_')[0]
                return {'role':'manager', 'category':category, 'group':found[0]['id']}
            found=list(r.table('groups').filter({'enrollment':{'advanced':code}}).run(db.conn))
            if len(found) > 0:
                category = found[0]['parent_category'] #found[0]['id'].split('_')[0]
                return {'role':'advanced', 'category':category, 'group':found[0]['id']}
            found=list(r.table('groups').filter({'enrollment':{'user':code}}).run(db.conn))
            if len(found) > 0:
                category = found[0]['parent_category'] #found[0]['id'].split('_')[0]
                return {'role':'user', 'category':category, 'group':found[0]['id']}
        raise CodeNotFound

    def CategoryGet(self,category_id):
        with app.app_context():        
            category = r.table('categories').get(category_id).run(db.conn)
        if category is None:
            raise CategoryNotFound

        return { 'name': category['name'] }


### USER Schema

    def CategoryGroupCreate(self,category_name,group_name,category_limits=False,category_quota=False,group_quota=False):
        category_id=_parse_string(category_name)
        group_id=_parse_string(group_name)
        with app.app_context():
            category = r.table('categories').get(category_id).run(db.conn)
            if category == None:                 
                category = {
                        "description": "" ,
                        "id": category_id ,
                        "limits": category_limits ,
                        "name": category_id ,
                        "quota": category_quota
                    }                
                r.table('categories').insert(category).run(db.conn)

            group = r.table('groups').get(group_id).run(db.conn)
            if group == None:
                group = {
                        "description": "" ,
                        "id": category_id+'-'+group_id ,
                        "limits": False ,
                        "parent_category": category_id,
                        "uid": group_id,
                        "name": group_id,
                        "enrollment": {'manager':False, 'advanced':False, 'user':False},
                        "quota": group_quota
                    }
                r.table('groups').insert(group).run(db.conn)                    
        return group['quota']