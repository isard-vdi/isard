# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

##
# WARNING: Duplicated code of webapp/webapp/webapp/config/ldapauth.py
##

import time
from rethinkdb import RethinkDB

from api import app
from ..libv2.flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)

'''
Modify this class as you need for your ldap.
Be sure to return all keys included in example user dictionaries.
'''
class myLdapAuth(object):
    def __init__(self):
        None
        
    def newUser(self,id,info):
        '''
        Here you have a generic_user that you can fill with your data.
        You can parse ldap info data as you want to reflect it on dict.
        As an example there is myuser that calls other functions to get
        the correct data for each key in dict.
        '''
        '''
        generic_user={  'id':username,
                        'name':username
                        'kind':'ldap',
                        'username':username,
                        'password':None,
                        'role':'user',
                        'category':'generic',
                        'group':'generic',
                        'email':'',
                        'quota':setUserQuota('user')
            }
        '''
        username=id.split('-')[-1]
        category = self._setUserCategory(username,info)
        group = self._setUserGroup(username,info)
        myuser={'id': 'ldap-'+category+'-'+username+'-'+username,
                    'name': username if 'displayName' not in info[1].keys() else info[1]['displayName'][0].decode('utf-8'),
                    'uid': username,
                    'provider': 'ldap',
                    'active': True,
                    'accessed': time.time(),
                    'username': username,
                    'password': None,
                    'role': self._setUserRole(username),
                    'category': category,
                    'group': category+'-'+group,
                    'email': info[1]['mail'][0].decode('utf-8'),
                    'photo': None,
                    'default_templates':[],
                    'quota': self._setQuota(self._setUserRole(username), category, group),
                    'group_uid': category+'-'+group
                    }
        return myuser

    def _setUserCategory(self,username,info):
        return info[1]["homeDirectory"][0].decode('utf-8').split("/home/users/")[1].split("/"+username)[0].split('/')[0]

    def _setUserGroup(self,username,info):
        return info[1]["homeDirectory"][0].decode('utf-8').split("/home/users/")[1].split("/"+username)[0].split('/')[1]
                
    def _setUserRole(self,username):
        if any(char.isdigit() for char in username):
            return 'user'
        else:
            return 'advanced'

    '''
    Get quotas from 'roles' table based on role. This should be a dictionary.
    Please connect to your rethink database and query for roles table.
    '''
    def _setQuota(self,role_id,category_id,group_id):
        with app.app_context():
            category = r.table('categories').get(category_id).run(db.conn)
            if category == None:
                category = {
                        "description": "" ,
                        "id": category_id ,
                        "limits": {
                            "desktops": 200 ,
                            "desktops_disk_size": 40 ,
                            "isos": 4 ,
                            "isos_disk_size": 0 ,
                            "memory": 200 ,
                            "running": 100 ,
                            "templates": 20 ,
                            "templates_disk_size": 0 ,
                            "users": 400 ,
                            "vcpus": 200
                        } ,
                        "name": category_id ,
                        "quota": {
                            "desktops": 3 ,
                            "desktops_disk_size": 40 ,
                            "isos": 0 ,
                            "isos_disk_size": 0 ,
                            "memory": 6 ,
                            "running": 2 ,
                            "templates": 0 ,
                            "templates_disk_size": 0 ,
                            "vcpus": 6
                        }
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
                        "quota": {
                            "desktops": 3 if role_id == 'user' else 6,
                            "desktops_disk_size": 40 ,
                            "isos": 0 if role_id == 'user' else 2,
                            "isos_disk_size": 0 ,
                            "memory": 6 if role_id == 'user' else 12,
                            "running": 2 if role_id == 'user' else 4,
                            "templates": 0 if role_id == 'user' else 4,
                            "templates_disk_size": 0 ,
                            "vcpus": 6 if role_id == 'user' else 12,
                        }
                    }
                r.table('groups').insert(group).run(db.conn)                    
        return group['quota']
