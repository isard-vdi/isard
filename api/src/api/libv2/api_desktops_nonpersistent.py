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

class ApiDesktopsNonPersistent():
    def __init__(self):
        None

    def New(self,user_id,template_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) is None:
                raise UserNotFound
        # Has a desktop with this template? Then return it (start it if stopped)
        with app.app_context():
            desktops = list(r.db('isard').table('domains').get_all(user_id, index='user').filter({'from_template':template_id, 'persistent':False}).run(db.conn))
        if len(desktops) == 1:
            if desktops[0]['status'] == 'Started':
                return desktops[0]['id']
            elif desktops[0]['status'] == 'Stopped':
                ds.WaitStatus(desktops[0]['id'], 'Stopped','Starting','Started')
                return desktops[0]['id']

        # If not, delete all nonpersistent desktops based on this template from user
        ds.delete_non_persistent(user_id,template_id)

        # and get a new nonpersistent desktops from this template
        return self._nonpersistent_desktop_create_and_start(user_id,template_id)

    def Delete(self, desktop_id):
        with app.app_context():
            desktop = r.table('domains').get(desktop_id).run(db.conn)
        if desktop == None:
            raise DesktopNotFound
        ds.delete_desktop(desktop_id, desktop['status'])
        
    def DeleteOthers(self, user_id, template_id):
        ## Will delete everything but one from this template_id (if exists)
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) is None:
                raise UserNotFound
        
        ####### Delete all desktops not from this template
        with app.app_context():
            desktops = list(r.db('isard').table('domains').get_all(user_id, index='user').filter({'kind':'desktop', 'persistent':False}).run(db.conn))
        for desktop in desktops:
            if 'from_template' in desktop and desktop['from_template'] != template_id:
                ds.delete_desktop(desktop['id'], desktop['status'])

        ####### Get how many desktops are from this template and leave only one
        with app.app_context():
            desktops = list(r.db('isard').table('domains').get_all(user_id, index='user').filter({'kind':'desktop','from_template':template_id, 'persistent':False}).order_by(r.desc('accessed')).run(db.conn))       
        # This situation should not happen as there should only be a maximum of 1 non persistent desktop
        # So we delete all but the first one [0] as the descendant order_by lets this as the newer desktop 
        if len(desktops) > 1:
            for i in range(1,len(desktops)-1):
                ## We delete all and return the first as the order is descendant (first is the newer desktop)
                ds.delete_desktop(desktops[i]['id'])

        # No desktop already in system
        if len(desktops) == 0: 
            raise DesktopNotFound
        # Desktop, but stopped
        if desktops[0]['status'] == 'Stopped':
            raise DesktopNotStarted

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
                  'accessed': time.time(),
                  'persistent':False,
                  'from_template':template['id']}

        with app.app_context():
            if _check(r.table('domains').insert(new_desktop).run(db.conn),'inserted'):
                return new_desktop['id']
        return False


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

