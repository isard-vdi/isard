# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
import rethinkdb as r
from flask_login import LoginManager, UserMixin
import time

from webapp import app
from ..lib.flask_rethink import RethinkDB

db = RethinkDB(app)
db.init_app(app)
from ..lib.log import *

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

ram_users={}

class LocalUsers():
    def __init__(self):
        None
    
    def getUser(self,username):
        with app.app_context():
            usr=r.table('users').get(username).run(db.conn)
        return usr

class User(UserMixin):
    def __init__(self, dict):
        self.id = dict['id']
        self.username = dict['id']
        self.name = dict['name']
        self.password = dict['password']
        self.role = dict['role']
        self.category = dict['category']
        self.group = dict['group']
        self.mail = dict['mail']
        self.quota = dict['quota']
        self.is_admin=True if self.role=='admin' else False
        self.active = dict['active']

    def is_active(self):
        return self.active
    
    def is_anonymous(self):
        return False

def logout_ram_user(username):
    del(ram_users[username])
             
@login_manager.user_loader
def user_loader(username):
    if username not in ram_users:
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
    log.error('No ldap module found, disabling')
    
from ..config.ldapauth import myLdapAuth
class auth(object):
    def __init__(self):
        None


    def fakecheck(self,fakeuser,admin_password):
        return self.authentication_fakeadmin(fakeuser,admin_password)
        
          
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
        if local_user is not None:
            if local_user['kind']=='local' and local_auth['active']:
                user_validated = self.authentication_local(username,password)
                if user_validated:
                    self.update_access(username)
                    return user_validated
            if local_user['kind']=='ldap' and ldap_auth['active']:
                user_validated = self.authentication_ldap(username,password)
                if user_validated:
                    self.update_access(username)
                    return user_validated
            #~ if local_user['kind']=='google_oauth2':
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
            log.info('USER:'+username)
            if dbuser is None:
                return False
        pw=Password()
        if pw.valid(password,dbuser['password']):
            #~ TODO: Check active or not user
            return User(dbuser)
        else:
            return False
   

    def authentication_ldap(self,username,password,returnObject=True):
        cfg=r.table('config').get(1).run(db.conn)['auth']
        try:
            conn = ldap.initialize(cfg['ldap']['ldap_server'])
            id_conn = conn.search(cfg['ldap']['bind_dn'],ldap.SCOPE_SUBTREE,"uid=%s" % username)
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
            log.error("LDAP ERROR:",e)
            return False
            
    def authentication_fakeadmin(self,fakeuser,admin_password):
        with app.app_context():
            admin_dbuser=r.table('users').get('admin').run(db.conn)
            if admin_dbuser is None:
                return False
        pw=Password()
        if pw.valid(admin_password,admin_dbuser['password']):
            with app.app_context():
                dbuser=r.table('users').get(fakeuser).run(db.conn)
            if dbuser is None:
                return False
            else:
                dbuser['name']='FAKEUSER'
                #~ quota = admin_dbuser['quota']
                #~ {  'domains':{ 'desktops': 99,
                                                #~ 'templates':99,
                                                #~ 'running':  99},
                                    #~ 'hardware':{'vcpus':    8,
                                                #~ 'ram':      1000000}} # 10GB
                dbuser['quota']=admin_dbuser['quota']
                dbuser['role']='admin'
                ram_users[fakeuser]=dbuser
                return User(dbuser)
        else:
            return False   
   
    def update_access(self,username):
        with app.app_context():
            r.table('users').get(username).update({'accessed':time.time()}).run(db.conn)
            
'''
PASSWORDS MANAGER
'''
import bcrypt
class Password(object):
        def __init__(self):
            None

        def valid(self,plain_password,enc_password):
            return bcrypt.checkpw(plain_password.encode('utf-8'), enc_password.encode('utf-8'))
                
        def encrypt(self,plain_password):
            return bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
