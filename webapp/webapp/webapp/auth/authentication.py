# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
import rethinkdb as r
from flask import request
from flask_login import LoginManager, UserMixin
import time
import requests

from webapp import app
from ..lib.flask_rethink import RethinkDB

db = RethinkDB(app)
db.init_app(app)
from ..lib.log import *
import traceback

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "redirect_to_login"

ram_users={}

class LocalUsers():
    def __init__(self):
        None
    
    def getUser(self,username):
        with app.app_context():
            usr=r.table('users').get(username).run(db.conn)
            if usr is None:
                return None
            usr['group_uid']= r.table('groups').get(usr['group']).pluck('uid').run(db.conn)['uid']
        return usr

class User(UserMixin):
    def __init__(self, dict):
        self.id = dict['id']
        self.provider = dict['provider']
        self.category = dict['category']
        self.uid = dict['uid']
        self.username = dict['username']
        self.name = dict['name']
        self.password = dict['password']
        self.role = dict['role']
        self.group = dict['group']
        self.path = dict['category']+'/'+dict['group_uid']+'/'+dict['provider']+'/'+dict['uid']+'-'+dict['username']+'/'
        self.email = dict['email']
        self.quota = dict['quota']
        self.auto = dict['auto'] if 'auto' in dict.keys() else False
        self.is_admin=True if self.role=='admin' else False
        self.active = dict['active']
        self.tags = [] if 'tags' not in dict.keys() else dict['tags']

    def is_active(self):
        return self.active
    
    def is_anonymous(self):
        return False


def get_authenticated_user_backend():
    """Check if session is authenticated by backend

    :returns: User object if authenticated
    """
    response = requests.get(
        'http://isard-backend:8080/api/v2/check',
        cookies={'session': request.cookies.get('session')}
    )
    if response.status_code == 200:
        user = app.localuser.getUser(response.text)
        if user:
            return User(user)
    return None


def logout_backend(response):
    """Send logout to backend

    :param response: Flask response
    :return: True if successful, otherwise False
    """
    cookies = {}
    for name, value in request.cookies.items():
        cookies[name] = value
    backend_response = requests.get(
        'http://isard-backend:8080/api/v2/logout/remote',
        cookies=cookies,
        allow_redirects=False
    )
    if backend_response.status_code != 200:
        log.error('backend remote logout failed')
        return False
    response.set_cookie('session', expires=0)
    response.set_cookie('isard', expires=0)
    return True


def logout_ram_user(username):
    del(ram_users[username])
             
@login_manager.user_loader
def user_loader(username):
    if username not in ram_users:
        user=app.localuser.getUser(username)
        if user is None: return
        ram_users[username]=user
    return User(ram_users[username])

def user_reloader(username):
    user=app.localuser.getUser(username)
    if user is None: return
    ram_users[username]=user
    return User(ram_users[username])
'''
LOCAL AUTHENTICATION AGAINS RETHINKDB USERS TABLE
'''
try:
    import ldap
except Exception as e:
    log.warning('No ldap module found, disabling ldap authentication')
    
from ..config.ldapauth import myLdapAuth
class auth(object):
    def __init__(self):
        None
          
    def check(self,username,password):
        if username=='admin':
            user_validated=self.authentication_local(username,password)
            if user_validated:
                self.update_access(username)
                return user_validated
        with app.app_context():
            cfg=r.table('config').get(1).run(db.conn)
        if cfg is None:
            return False
        ldap_auth=cfg['auth']['ldap']
        local_auth=cfg['auth']['local']
        local_user=r.table('users').get(username).run(db.conn)
        if local_user != None:
            if local_user['provider']=='local' and local_auth['active']:
                user_validated = self.authentication_local(username,password)
                if user_validated:
                    self.update_access(username)
                    return user_validated
            if local_user['provider']=='ldap' and ldap_auth['active']:
                user_validated = self.authentication_ldap(username,password)
                if user_validated:
                    self.update_access(username)
                    return user_validated
            #~ if local_user['provider']=='google_oauth2':
                #~ return self.authentication_googleOauth2(username,password)
        else:
            if ldap_auth['active']:
                user_validated=self.authentication_ldap(username,password)
                if user_validated:
                    user=self.authentication_ldap(username,password,returnObject=False)
                    if r.table('categories').get(user['category']).run(db.conn) is None:
                        r.table('categories').insert({  'id':user['category'],
                                                        'name':user['category'],
                                                        'description':'',
                                                        'quota':r.table('roles').get(user['role']).run(db.conn)['quota']}).run(db.conn)
                    if r.table('groups').get(user['group']).run(db.conn) is None:
                        r.table('groups').insert({  'id':user['group'],
                                                        'name':user['group'],
                                                        'description':'',
                                                        'quota':r.table('categories').get(user['category']).run(db.conn)['quota']}).run(db.conn)
                    r.table('users').insert(user).run(db.conn)
                    self.update_access(username)
                    return User(user)
                else:
                    return False
        return False
        
    def authentication_local(self,username,password):
        with app.app_context():
            dbuser=r.table('users').get(username).run(db.conn)
            #log.info('USER:'+username)
            if dbuser is None or dbuser['active'] is not True:
                return False
            dbuser['group_uid']=r.table('groups').get(dbuser['group']).pluck('uid').run(db.conn)['uid']
        pw=Password()
        if pw.valid(password,dbuser['password']):
            #~ TODO: Check active or not user
            return User(dbuser)
        else:
            return False
   

    def authentication_ldap(self,username,password,returnObject=True):
        with app.app_context():
            cfg=r.table('config').get(1).run(db.conn)['auth']
        try:
            conn = ldap.initialize(cfg['ldap']['ldap_server'])
            id_conn = conn.search(cfg['ldap']['bind_dn'],ldap.SCOPE_SUBTREE,"uid=%s" % username.split('-')[-1])
            tmp,info=conn.result(id_conn, 0)
            user_dn=info[0][0]
            if conn.simple_bind_s(who=user_dn,cred=password):
                '''
                config/ldapauth.py has the function you can change to adapt to your ldap
                '''
                au=myLdapAuth()
                newUser=au.newUser(username,info[0])
                return User(newUser) if returnObject else newUser
            else:
                return False
        except Exception as e:
            #print(traceback.format_exc())
            log.error("LDAP ERROR: "+str(e))
            return False 
   
    def update_access(self,username):
        with app.app_context():
            r.table('users').get(username).update({'accessed':time.time()}).run(db.conn)

    def ldap_users_exists(self,commit=False):
        with app.app_context():
            cfg=r.table('config').get(1).run(db.conn)['auth']
        users=list(r.table('users').filter({'active':True,'provider':'ldap'}).pluck('id','name','accessed').run(db.conn))
        nonvalid=[]
        valid=[]
        for u in users:
            conn = ldap.initialize(cfg['ldap']['ldap_server'])
            id_conn = conn.search(cfg['ldap']['bind_dn'],ldap.SCOPE_SUBTREE,"uid=%s" % u['id'])
            tmp,info=conn.result(id_conn, 0)
            if len(info):
                valid.append(u)
            else:
                nonvalid.append(u)
        if commit:
            nonvalid_list= [ u['id'] for u in nonvalid ]
            return r.table('users').get_all(r.args(nonvalid_list)).update({'active':False}).run(db.conn)
        else:
            return {'nonvalid':nonvalid,'valid':valid}
               
'''
PASSWORDS MANAGER
'''
import bcrypt,string,random
class Password(object):
        def __init__(self):
            None

        def valid(self,plain_password,enc_password):
            try:
                return bcrypt.checkpw(plain_password.encode('utf-8'), enc_password.encode('utf-8'))
            except:
                # If password is too short could lead to 'Invalid salt' Exception
                return False

        def encrypt(self,plain_password):
            return bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        def generate_human(self,length=6):
            chars = string.ascii_letters + string.digits + '!@#$*'
            rnd = random.SystemRandom()
            return ''.join(rnd.choice(chars) for i in range(length))
        
