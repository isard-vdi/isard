# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
import time
from webapp import app
from werkzeug.utils import secure_filename

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

from .flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from collections import defaultdict

from .ds import DS
ds = DS()


class TemplateTree():
    def __init__(self):
        None

    ''' NEW TEMPLATE TREES '''
    def get_tree(self, template_id, current_user):
        levels = {}
        derivated = self.tree_template_list(template_id, current_user)
        for n in derivated:
            levels.setdefault(n['parent'], []).append(n)
        recursion = self.template_recursion_tree(template_id,levels)
        with app.app_context():
            d = r.db('isard').table('domains').get(template_id).pluck('id','name','kind','category','group','user','username','status','parents').run(db.conn)        
        root = [{'id': d['id'],
                'title': d['name'],
                'expanded': True,
                'unselectable': False if current_user.role == "manager" or current_user.role == "admin" else True,
                'selected': True if current_user.id == d['user'] else False,
                'parent': d['parents'][-1] if 'parents' in d.keys() and len(d['parents']) > 0 else '',
                'user': d['username'],
                'category': d['category'],
                'group': d['group'].split(d['category']+'-')[1],
                'kind': d['kind'] if d['kind']=='desktop' else 'template',
                'status': d['status'],
                'icon': "fa fa-desktop" if d['kind']=='desktop' else "fa fa-cube",
                'children': recursion}] 
        return root

    def template_recursion_tree(self, template_id, levels):
        nodes = [dict(n) for n in levels.get(template_id, [])]
        for n in nodes:
            children = self.template_recursion_tree(n['id'],levels)
            if children: n['children'] = children
            for c in children:
                if c['unselectable']==True: 
                    n['unselectable']=True
                    break
            #if n['unselectable']==True: n['title']=n['title']+ '-unselectable'
        return nodes

    def tree_template_list(self, template_id, current_user):
        with app.app_context():
            template = r.db('isard').table('domains').get(template_id).pluck('id','name','kind','category','group','user','username','status','parents').run(db.conn)
            derivated = list(r.db('isard').table('domains').pluck('id','name','kind','category','group','user','username','status','parents').filter(lambda derivates: derivates['parents'].contains(template_id)).run(db.conn))
        if current_user.role == "manager":
            if template['category'] != current_user.category: return []
            derivated = [d for d in derivated if d['category'] == current_user.category]
        fancyd = []
        for d in derivated:
            if current_user.role == "manager" or current_user.role == "admin":
                fancyd.append({ 'id': d['id'],
                                'title': d['name'],
                                'expanded': True,
                                'unselectable': False,
                                'selected': True if current_user.id == d['user'] else False,
                                'parent': d['parents'][-1],
                                'user': d['username'],
                                'category': d['category'],
                                'group': d['group'].split(d['category']+'-')[1],
                                'kind': d['kind'] if d['kind']=='desktop' else 'template',
                                'status': d['status'],
                                'icon': "fa fa-desktop" if d['kind']=='desktop' else "fa fa-cube" })                  
            else:     ## It can only be an advanced user 
                fancyd.append({ 'id': d['id'],
                                'title': d['name'],
                                'expanded': True,
                                'unselectable': False if current_user.id == d['user'] else True,
                                'selected': True if current_user.id == d['user'] else False,
                                'parent': d['parents'][-1],
                                'user': d['username'],
                                'category': d['category'],
                                'group': d['group'].split(d['category']+'-')[1],
                                'kind': d['kind'] if d['kind']=='desktop' else 'template',
                                'status': d['status'],
                                'icon': "fa fa-desktop" if d['kind']=='desktop' else "fa fa-cube" })                                                         
        return fancyd

