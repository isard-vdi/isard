# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import rethinkdb as r

from webapp import app
from ..lib.flask_rethink import RethinkDB

db = RethinkDB(app)
db.init_app(app)

'''
Modify this class as you need for your ldap.
Be sure to return all keys included in example user dictionaries.
'''
class myLdapAuth(object):
    def __init__(self):
        None
        
    def newUser(self,username,info):
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
        category = self._setUserCategory(username,info)
        group = self._setUserGroup(username,info)
        myuser={  'id':'ldap_'+category+'_'+username+'_'+username,
                'name':username if 'displayName' not in info[1].keys() else info[1]['displayName'][0].decode('utf-8'),
                'provider':'ldap',
                'uid': username,
                'active':True,
                'username':username,
                'password':None,
                'role':self._setUserRole(username),
                'category':category,
                'group':category+'_'+group,
                'email':info[1]['email'][0].decode('utf-8'),
                'quota':self_setQuota(group)
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
    def _setQuota(self,group_id):
        with app.app_context():
            group = r.table('groups').get(group_id).run(db.conn)
        return group['quota']
