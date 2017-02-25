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
import rethinkdb as r

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
        
    '''
    ADMIN API
    '''
    def toggle_hypervisor_field(self,id,key):
        with app.app_context():
            field=r.table('hypervisors').get(id).run(db.conn)[key]
            new_field=False if field else True
            return self.check(r.table('hypervisors').get(id).update({key:new_field}).run(db.conn),'replaced')
                
    def get_admin_user(self):
        with app.app_context():
            ## ALERT: Should remove password (password='')
            return self.f.table_values_bstrap(r.table('users').run(db.conn))

    def get_admin_table(self, table, pluck=False):
        with app.app_context():
            if pluck:
                return self.f.table_values_bstrap(r.table(table).pluck(pluck).run(db.conn))
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
                
    def update_table_dict(self, table, id, dict):
        with app.app_context():
            return self.check(r.table(table).get(id).update(dict).run(db.conn), 'replaced')
            return True 

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
