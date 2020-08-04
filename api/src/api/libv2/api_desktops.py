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

class ApiDesktops():
    def __init__(self):
        None


    """ def DesktopNewPersistent(self,user_id,template_id, desktop_name):
        parsed_name = _parse_string(desktop_name)
        desktop_id = '_' + user_id +  + parsed_name
        with app.app_context():
            desktops = r.db('isard').table('domains').get(desktop_id).run(db.conn)
        if len(desktops) != None:
            raise DesktopExists

        return self._nonpersistent_desktop_create_and_start(user_id,template_id,desktop_name) """

    def DesktopNewNonpersistent(self,user_id,template_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) is None:
                raise UserNotFound
        # Has a desktop with this template? Then return it (start it if stopped)
        with app.app_context():
            desktops = list(r.db('isard').table('domains').get_all(user_id, index='user').filter({'from_template':template_id, 'persistent':False}).run(db.conn))
        if len(desktops) == 1:
         with app.app_context():
            desktops = list(r.db('isard').table('domains').get_all(user_id, index='user').filter({'from_template':template_id, 'persistent':False}).run(db.conn))
        if len(desktops) == 1:
            if desktops[0]['status'] == 'Started':
                return desktops[0]['id']
            elif desktops[0]['status'] == 'Stopped':
                ds.WaitStatus(desktops[0]['id'], 'Stopped','Starting','Started')
                return desktops[0]['id']

        # If not, delete all nonpersistent based desktops from user
        ds.delete_non_persistent(user_id,template_id)

        # and get a new nonpersistent desktops from this template
        return self._nonpersistent_desktop_create_and_start(user_id,template_id)

    def DesktopViewer(self, desktop_id, protocol):
        try:
            viewer_txt = isardviewer.viewer_data(desktop_id, protocol, get_cookie=False)
        except DesktopNotFound:
            raise
        except DesktopNotStarted:
            raise
        except NotAllowed:
            raise
        except ViewerProtocolNotFound:
            raise
        except ViewerProtocolNotImplemented:
            raise
        return viewer_txt

    def DesktopDelete(self, desktop_id):
        with app.app_context():
            desktop = r.table('domains').get(desktop_id).run(db.conn)
        if desktop == None:
            raise DesktopNotFound
        ds.delete_desktop(desktop_id, desktop['status'])

    def _nonpersistent_desktop_create_and_start(self, user_id, template_id):
        with app.app_context():
            user=r.table('users').get(user_id).run(db.conn)
        if user == None:
            raise UserNotFound
        # Create the domain from that template
        desktop_id = self._nonpersistent_desktop_from_tmpl(user_id, user['category'], user['group'], template_id)
        if desktop_id is False :
            raise DesktopNotCreated

        ds.WaitStatus(desktop_id, 'Any','Any','Started')
        return desktop_id

    def _nonpersistent_desktop_from_tmpl(self, user_id, category, group, template_id):
        with app.app_context():
            template = r.table('domains').get(template_id).run(db.conn)
        if template == None:
            raise TemplateNotFound
        timestamp = time.strftime("%Y%m%d%H%M%S")
        parsed_name=timestamp+'-'+_parse_string(template['name'])

        parent_disk=template['hardware']['disks'][0]['file']
        dir_disk = 'volatiles/'+category+'/'+group+'/'+user_id
        disk_filename = parsed_name+'.qcow2'

        create_dict=template['create_dict']
        create_dict['hardware']['disks']=[{'file':dir_disk+'/'+disk_filename,
                                            'parent':parent_disk}]
        create_dict=_parse_media_info(create_dict)

        new_desktop={'id': '_'+user_id+'-'+parsed_name,
                  'name': parsed_name,
                  'description': template['description'],
                  'kind': 'desktop',
                  'user': user_id,
                  'username': user_id.split('-')[-1],
                  'status': 'CreatingAndStarting',
                  'detail': None,
                  'category': category,
                  'group': group,
                  'xml': None,
                  'icon': template['icon'],
                  'server': template['server'],
                  'os': template['os'],
                  'options': {'viewers':{'spice':{'fullscreen':True}}},
                  'create_dict': {'hardware':create_dict['hardware'],
                                    'origin': template['id']},
                  'hypervisors_pools': template['hypervisors_pools'],
                  'allowed': {'roles': False,
                              'categories': False,
                              'groups': False,
                              'users': False},
                  'persistent':False,
                  'from_template':template['id']}

        with app.app_context():
            if _check(r.table('domains').insert(new_desktop).run(db.conn),'inserted'):
                return new_desktop['id']
        return False

    def DesktopNewPersistent(self, desktop_name, user_id,  memory, vcpus, from_template_id = False, xml_id = False, disk_size = False, iso = False, boot='disk'):
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
                  'kind': 'desktop',
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







