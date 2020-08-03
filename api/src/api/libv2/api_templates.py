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

from .apiv2_exc import *

from .ds import DS 
ds = DS()

from .helpers import _check, _parse_string, _parse_media_info, __disk_path 

class ApiTemplates():
    def __init__(self):
        None



    def TemplateNew(self, template_name, user_id, from_desktop_id):
        parsed_name = _parse_string(template_name)
        template_id = '_' + user_id + '-' + parsed_name

        with app.app_context():
            try:
                user=r.table('users').get(user_id).pluck('id','category','group','provider','username','uid').run(db.conn)
            except:
                raise UserNotFound
            desktop = r.table('domains').get(from_desktop_id).run(db.conn)
            if desktop == None: raise DesktopNotFound

        parent_disk=desktop['hardware']['disks'][0]['file']

        hardware = desktop['create_dict']['hardware']

        dir_disk, disk_filename = _disk_path(user, parsed_name)
        hardware['disks']=[{'file':dir_disk+'/'+disk_filename,
                                            'parent':parent_disk}]

        create_dict=_parse_media_info({'hardware':hardware})
        create_dict['origin']=from_desktop_id
        print(create_dict)
        template_dict={'id': template_id,
                  'name': template_name,
                  'description': 'Api created',
                  'kind': 'user_template',
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
                  'create_dict': create_dict,
                  'hypervisors_pools': ['default'],
                  'parents': desktop['parents'] if 'parents' in desktop.keys() else [],
                  'allowed': {'roles': False,
                              'categories': False,
                              'groups': False,
                              'users': False}}

        with app.app_context():
            if r.table('domains').get(template_dict['id']).run(db.conn) == None:

                if _check(r.table('domains').get(from_desktop_id).update({"create_dict": {"template_dict": template_dict}, "status": "CreatingTemplate"}).run(db.conn),'replaced') == False:
                    raise NewTemplateNotInserted
                else:
                    return template_dict['id']
            else:
                raise TemplateExists







