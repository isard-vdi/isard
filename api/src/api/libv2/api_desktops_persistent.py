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

from ..libv2.isardViewer import isardViewer
isardviewer = isardViewer()

from .apiv2_exc import *

from .ds import DS 
ds = DS()

from .helpers import _check, _parse_string, _parse_media_info, _disk_path

class ApiDesktopsPersistent():
    def __init__(self):
        None

    def Delete(self, desktop_id):
        with app.app_context():
            desktop = r.table('domains').get(desktop_id).run(db.conn)
        if desktop == None:
            raise DesktopNotFound
        ds.delete_desktop(desktop_id, desktop['status'])

    def New(self, desktop_name, user_id,  memory, vcpus, kind = 'desktop', from_template_id = False, xml_id = False, xml_definition = False, disk_size = False, disk_path = False, parent_disk_path=False, iso = False, boot='disk'):
        if kind not in ['desktop', 'user_template']:
            raise NewDesktopNotInserted
        parsed_name = _parse_string(desktop_name)
        hardware = {'boot_order': [boot],
                    'disks': [],
                    'floppies': [],
                    'graphics': ['default'],
                    'interfaces': ['default'],
                    'isos': [],
                    'memory': 524288,
                    'vcpus': 1,
                    'videos': ['default']}

        with app.app_context():
            try:
                user=r.table('users').get(user_id).pluck('id','category','group','provider','username','uid').run(db.conn)
            except:
                raise UserNotFound
            if iso != False:
                if r.table('media').get(iso).run(db.conn) == None: raise MediaNotFound
            if from_template_id != False:
                template = r.table('domains').get(from_template_id).run(db.conn)
                if template == None: raise TemplateNotFound
                xml = None
            elif xml_id != False:
                xml_data = r.table('virt_install').get(xml_id).run(db.conn)
                if xml_data == None: raise XmlNotFound
                xml = xml_data['xml']
            elif xml_definition != False:
                xml = xml_definition
            else:
                raise DesktopPreconditionFailed


        dir_disk, disk_filename = _disk_path(user, parsed_name)

        if from_template_id == False:
            if disk_size == False:
                if boot == 'disk': raise NewDesktopNotBootable
                if boot == 'cdrom' and iso == False: raise NewDesktopNotBootable
                hardware['disks']=[]
            else:
                hardware['disks']=[{'file':dir_disk+'/'+disk_filename,
                                    'size':disk_size}]   # 15G as a format   UNITS NEEDED!!!
            status = 'CreatingDiskFromScratch'
            parents = []
        if disk_path:
            if not parent_disk_path:
                parent_disk_path = ''
            hardware['disks'] = [{
                'file': disk_path,
                'parent': parent_disk_path
            }]
            status = 'Updating'
        else:
            hardware['disks']=[{'file':dir_disk+'/'+disk_filename,
                                                'parent':template['create_dict']['hardware']['disks'][0]['file']}]
            status = 'Creating'
            parents = template['parents'] if 'parents' in template.keys() else []

        hardware['boot_order']=[boot]
        hardware['isos']=[] if iso == False else [iso]
        hardware['vcpus']=vcpus
        hardware['memory']=memory*1048576

        create_dict=_parse_media_info({'hardware':hardware})
        if from_template_id != False:
            create_dict['origin']=from_template_id
        else:
            create_dict['create_from_virt_install_xml'] = xml_id

        new_domain={'id': '_'+user_id+'-'+parsed_name,
                  'name': desktop_name,
                  'description': 'Api created',
                  'kind': kind,
                  'user': user['id'],
                  'username': user['username'],
                  'status': status,
                  'detail': None,
                  'category': user['category'],
                  'group': user['group'],
                  'xml': xml,
                  'icon': 'linux',
                  'server': False,
                  'os': 'linux',
                  'options': {'viewers':{'spice':{'fullscreen':True}}},
                  'create_dict': create_dict,
                  'hypervisors_pools': ['default'],
                  #'parents': parents,
                  'allowed': {'roles': False,
                              'categories': False,
                              'groups': False,
                              'users': False}}

        with app.app_context():
            if r.table('domains').get(new_domain['id']).run(db.conn) == None:
                if _check(r.table('domains').insert(new_domain).run(db.conn),'inserted') == False:
                    raise NewDesktopNotInserted
                else:
                    return new_domain['id']
            else:
                raise DesktopExists

    def UserDesktop(self, desktop_id):
        try:
            with app.app_context():
                return r.table('domains').get(desktop_id).pluck('user').run(db.conn)['user']
        except:
            raise DesktopNotFound

    def Start(self, desktop_id):
        with app.app_context():
            desktop = r.table('domains').get(desktop_id).run(db.conn)
        if desktop == None:
            raise DesktopNotFound
        # Start the domain
        ds.WaitStatus(desktop_id, 'Any', 'Starting', 'Started')
        return desktop_id

    def Stop(self, desktop_id):
        with app.app_context():
            desktop = r.table('domains').get(desktop_id).run(db.conn)
        if desktop == None:
            raise DesktopNotFound
        # Start the domain
        ds.WaitStatus(desktop_id, 'Any', 'Stopping', 'Stopped')
        return desktop_id
