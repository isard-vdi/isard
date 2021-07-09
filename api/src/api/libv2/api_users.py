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
from rethinkdb.errors import ReqlTimeoutError, ReqlNonExistenceError

import logging
import traceback

from .flask_rethink import RDB
db = RDB(app)
db.init_app(app)

from ..auth.authentication import *

from ..libv2.isardViewer import isardViewer
isardviewer = isardViewer()

from .apiv2_exc import *

from .helpers import (
    _check,
    _parse_string,
    _parse_media_info,
    _disk_path,
    _random_password,
    _parse_desktop,
)

from .ds import DS 
ds = DS()

from jose import jwt
import os
import bcrypt
import secrets
import requests

def check_category_domain(category_id, domain):
    with app.app_context():
        allowed_domain = (
            r.table("categories")
            .get(category_id)
            .pluck("allowed_domain")
            .run(db.conn)
            .get("allowed_domain")
        )
    return not allowed_domain or domain == allowed_domain


class ApiUsers():
    def __init__(self):
        self.au=auth()

    def Jwt(self,user_id):
        # user_id = provider_id+'-'+category_id+'-'+id+'-'+id
        try:
            with app.app_context():
                user = r.table('users').get(user_id).pluck('id','username','photo','email','role','category','group').run(db.conn)
                user = {'user_id':user['id'],
                        'role_id':user['role'],
                        'category_id':user['category'],
                        'group_id':user['group'],
                        'username':user['username'],
                        'email':user['email'],
                        'photo':user['photo']}
        except:
            raise UserNotFound
        return {'jwt':jwt.encode({"exp": datetime.utcnow() + timedelta(hours=4),
                                    "kid":"isardvdi",
                                    "data":user}, 
                                    app.ram['secrets']['isardvdi']['secret'], 
                                    algorithm='HS256')}

    def Login(self,user_id,user_passwd, provider='local', category_id='default'):
        with app.app_context():
            user = r.table('users').get(user_id).run(db.conn)
        if user is None or not user.get('active',False):
            raise UserLoginFailed

        pw=Password()
        if pw.valid(user_passwd,user['password']):
            user = {'user_id':user['id'],
                    'role_id':user['role'],
                    'category_id':user['category'],
                    'group_id':user['group'],
                    'username':user['username'],
                    'email':user['email'],
                    'photo':user['photo']}
            return user_id,jwt.encode({"exp": datetime.utcnow() + timedelta(hours=4),
                                        "kid":"isardvdi",
                                        "data":user}, 
                                        app.ram['secrets']['isardvdi']['secret'], 
                                        algorithm='HS256')
        raise UserLoginFailed

    def Exists(self,user_id):
        with app.app_context():
            user = r.table('users').get(user_id).run(db.conn)
        if user is None:
            raise UserNotFound
        return user

    def List(self):
        with app.app_context():
            return list(r.table('users').without('password','vpn').run(db.conn))
            
    def Create(self, provider, category_id, user_uid, user_username, name, role_id, group_id, password=False, encrypted_password=False, photo='', email=''):
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
            else:
                bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            if encrypted_password != False:
                password = encrypted_password

            user = {'id': id,
                    'name': name,
                    'uid': user_uid,
                    'provider': provider,
                    'active': True,
                    'accessed': time.time(),
                    'username': user_username,
                    'password': password,
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

    def Update(self, user_id, user_name=False, user_email=False, user_photo=False):
        self.Exists(user_id)
        with app.app_context():
            user = r.table("users").get(user_id).run(db.conn)
            if user is None:
                raise UserNotFound
            update_values = {}
            if user_name:
                update_values["name"] = user_name
            if user_email:
                update_values["email"] = user_email
            if user_photo:
                update_values["photo"] = user_photo
            if update_values:
                if not _check(
                    r.table("users").get(user_id).update(update_values).run(db.conn),
                    "replaced",
                ):
                    raise UpdateFailed

    def Templates(self,payload):
        try:
            with app.app_context():
                data1 = r.table('domains').get_all('base', index='kind').order_by('name').pluck({'id','name','allowed','kind','category','group','icon','user','description'}).run(db.conn)
                data2 = r.table('domains').filter(r.row['kind'].match("template")).order_by('name').pluck({'id','name','allowed','kind','category','group','icon','user','description'}).run(db.conn)
            desktops = data1+data2
            alloweds=[]
            for desktop in desktops:
                # with app.app_context():
                #     desktop['username']=r.table('users').get(desktop['user']).pluck('name').run(db.conn)['name']
                if payload['role_id']=='admin':
                    alloweds.append(desktop)
                    continue
                if payload['role_id']=='manager' and payload['category_id'] == desktop['category']:
                    alloweds.append(desktop)
                    continue
                if not payload.get('user_id',False): continue
                if desktop['user']==payload['user_id']:
                    alloweds.append(desktop)
                    continue
                if desktop['allowed']['roles'] is not False:
                    if len(desktop['allowed']['roles'])==0:
                        alloweds.append(desktop)
                        continue
                    else:
                        if payload['role_id'] in desktop['allowed']['roles']:
                            alloweds.append(desktop)
                            continue
                if desktop['allowed']['categories'] is not False:
                    if len(desktop['allowed']['categories'])==0:
                        alloweds.append(desktop)
                        continue
                    else:
                        if payload['category_id'] in desktop['allowed']['categories']:
                            alloweds.append(desktop)
                            continue
                if desktop['allowed']['groups'] is not False:
                    if len(desktop['allowed']['groups'])==0:
                        alloweds.append(desktop)
                        continue
                    else:
                        if payload['group_id'] in desktop['allowed']['groups']:
                            alloweds.append(desktop)
                            continue
                if desktop['allowed']['users'] is not False:
                    if len(desktop['allowed']['users'])==0:
                        alloweds.append(desktop)
                        continue
                    else:
                        if payload['user_id'] in desktop['allowed']['users']:
                            alloweds.append(desktop)
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
                desktops = list(
                    r.table("domains")
                    .get_all(user_id, index="user")
                    .filter({"kind": "desktop"})
                    .order_by("name")
                    .pluck(
                        [
                            "id",
                            "name",
                            "icon",
                            "image",
                            "user",
                            "status",
                            "description",
                            "parents",
                            "persistent",
                            "os",
                            "tag_visible",
                            {"viewer": "guest_ip"},
                            {"create_dict": {"hardware": ["interfaces", "videos"]}},
                        ]
                    )
                    .run(db.conn)
                )
            return [_parse_desktop(desktop) for desktop in desktops if desktop.get("tag_visible", True)]
        except Exception as e:
            error = traceback.format_exc()
            logging.error(error)
            raise UserDesktopsError

    def Desktop(self,desktop_id,user_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) == None:
                raise UserNotFound
        try:
            with app.app_context():
                desktop = r.table("domains") \
                    .get(desktop_id) \
                    .pluck(
                        [
                            "id",
                            "name",
                            "icon",
                            "image",
                            "user",
                            "status",
                            "description",
                            "parents",
                            "persistent",
                            "os",
                            "tag_visible",
                            {"viewer": "guest_ip"},
                            {"create_dict": {"hardware": ["interfaces", "videos"]}},
                        ]
                    ) \
                    .run(db.conn)

            # Modify desktop data to be returned
            if desktop.get("tag_visible", True):

                # if desktop["status"] not in ["Started", "Failed","Stopped"]:
                #     desktop["status"] = "Working"
                desktop["image"] = desktop.get("image", None)
                desktop["from_template"] = desktop.get("parents", [None])[-1]
                if desktop.get("persistent", True):
                    desktop["type"] = "persistent"
                else:
                    desktop["type"] = "nonpersistent"
                desktop["viewers"] = ["file-spice", "browser-vnc"]
                if desktop["status"] == "Started":
                    if "wireguard" in desktop["create_dict"]["hardware"]["interfaces"]:
                        desktop["ip"] = desktop.get("viewer", {}).get("guest_ip")
                        if not desktop["ip"]:
                            desktop["status"] = "WaitingIP"
                        if desktop["os"].startswith("win"):
                            desktop["viewers"].extend(["file-rdpvpn", "browser-rdp"])
                return desktop
            else:
                return None
        except ReqlNonExistenceError:
            raise DesktopNotFound
        except Exception as e:
            error = traceback.format_exc()
            logging.error(error)
            raise UserDesktopsError

    def Delete(self,user_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) is None:
                raise UserNotFound
        todelete = self._user_delete_checks(user_id)
        for desktop in todelete:
            try:
                ds.delete_desktop(desktop['id'],desktop['status'])
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
                #desktops = [d for d in derivated if desktop['kind'] == "desktop"]
        domains = user_desktops+user_templates+derivated
        return [i for n, i in enumerate(domains) if i not in domains[n + 1:]]

    def OwnsDesktop(self, user_id, guess_ip):
        with app.app_context():
            ips = list(r.table("domains").get_all(user_id, index='user').pluck({'viewer':'guest_ip'}).run(db.conn))
        if len([ip for ip in ips if ip.get('viewer', False) and ip['viewer'].get('guest_ip',False) == guess_ip]):
            return True
        raise DesktopNotFound
    
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

    def CategoryCreate(self,category_name,frontend=False,group_name=False,category_limits=False,category_quota=False,group_quota=False):
        category_id=_parse_string(category_name)
        if group_name:
            group_id=_parse_string(group_name)
        else:
            group_name='Main'
            group_id='main'
        with app.app_context():
            category = r.table('categories').get(category_id).run(db.conn)
            if category == None:
                category = {
                        "description": "" ,
                        "id": category_id ,
                        "limits": category_limits ,
                        "name": category_name ,
                        "quota": category_quota,
                        "frontend": frontend
                    }
                r.table('categories').insert(category, conflict='update').run(db.conn)

            group = r.table('groups').get(category_id+'-'+group_id).run(db.conn)
            if group == None:
                group = {
                        "description": "["+category['name']+"]" ,
                        "id": category_id+'-'+group_id ,
                        "limits": False ,
                        "parent_category": category_id,
                        "uid": group_id,
                        "name": group_name,
                        "enrollment": {'manager':False, 'advanced':False, 'user':False},
                        "quota": group_quota
                    }
                r.table('groups').insert(group, conflict='update').run(db.conn)
        return category_id

    def GroupCreate(self,category_id,group_name,category_limits=False,category_quota=False,group_quota=False):
        group_id=_parse_string(group_name)
        with app.app_context():
            category = r.table('categories').get(category_id).run(db.conn)
            if category == None: return False

            group = r.table('groups').get(category_id+'-'+group_id).run(db.conn)
            if group == None:
                group = {
                        "description": "["+category['name']+"]" ,
                        "id": category_id+'-'+group_id ,
                        "limits": False ,
                        "parent_category": category_id,
                        "uid": group_id,
                        "name": group_name,
                        "enrollment": {'manager':False, 'advanced':False, 'user':False},
                        "quota": group_quota
                    }
                r.table('groups').insert(group, conflict='update').run(db.conn)
        return category_id+'-'+group_id

    def CategoriesGet(self):
        with app.app_context():
            return list(r.table('categories').pluck({'id','name','frontend'}).order_by('name').run(db.conn))

    def CategoriesFrontendGet(self):
        with app.app_context():
            return list(r.table('categories').pluck({'id','name','frontend'}).filter({'frontend':True}).order_by('name').run(db.conn))

    def CategoryDelete(self, category_id):
        #### TODO: Delete all desktops, templates and users in category
        with app.app_context():
            r.table('users').get_all(category_id,index='category').delete().run(db.conn)
            r.table('groups').get_all(category_id,index='parent_category').delete().run(db.conn)
            return r.table('categories').get(category_id).delete().run(db.conn)

    def GroupsGet(self):
        with app.app_context():        
            return list(r.table('groups').order_by('name').run(db.conn))

    def GroupDelete(self, group_id):
        #### TODO: Delete all desktops, templates and users in category
        with app.app_context():
            r.table('users').get_all(group_id,index='group').delete().run(db.conn)
            return r.table('groups').get(group_id).delete().run(db.conn)

    def Secret(self,kid,description,role_id,category_id,domain):
        with app.app_context():
            ## TODO: Check if exists, check that role is correct and category exists
            secret = secrets.token_urlsafe(32)
            r.table('secrets').insert({'id':kid,
                                        'secret':secret,
                                        'description':description,
                                        'role_id':role_id,
                                        'category_id':category_id,
                                        'domain':domain}).run(db.conn)
        return secret

    def SecretDelete(self,kid):
        with app.app_context():
            ## TODO: Check if exists, check that role is correct and category exists
            secret = secrets.token_urlsafe(32)
            r.table('secrets').get(kid).delete().run(db.conn)
        return True

'''
PASSWORDS MANAGER
'''
import bcrypt,string,random
class Password(object):
        def __init__(self):
            None

        def valid(self,plain_password,enc_password):
            return bcrypt.checkpw(plain_password.encode('utf-8'), enc_password.encode('utf-8'))

        def encrypt(self,plain_password):
            return bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        def generate_human(self,length=6):
            chars = string.ascii_letters + string.digits + '!@#$*'
            rnd = random.SystemRandom()
            return ''.join(rnd.choice(chars) for i in range(length))