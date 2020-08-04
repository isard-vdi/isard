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


import bcrypt,string,random

from .apiv2_exc import *


def _parse_string( txt):
    import re, unicodedata, locale
    if type(txt) is not str:
        txt = txt.decode('utf-8')
    #locale.setlocale(locale.LC_ALL, 'ca_ES')
    prog = re.compile("[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$")
    if not prog.match(txt):
        return False
    else:
        # ~ Replace accents
        txt = ''.join((c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn'))
        return txt.replace(" ", "_")

def _disk_path( user, parsed_name):
    with app.app_context():
        group_uid = r.table('groups').get(user['group']).run(db.conn)['uid']

    dir_path = user['category']+'/'+group_uid+'/'+user['provider']+'/'+user['uid']+'-'+user['username']
    filename = parsed_name + '.qcow2'
    return dir_path,filename

def _check(dict,action):
    '''
    These are the actions:
    {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
    '''
    if dict[action]:
        return True
    if not dict['errors']: return True
    return False

def _random_password(length=16):
    chars = string.ascii_letters + string.digits + '!@#$*'
    rnd = random.SystemRandom()
    return ''.join(rnd.choice(chars) for i in range(length))

def _parse_media_info( create_dict):
    medias=['isos','floppies','storage']
    for m in medias:
        if m in create_dict['hardware']:
            newlist=[]
            for item in create_dict['hardware'][m]:
                with app.app_context():
                    newlist.append(r.table('media').get(item['id']).pluck('id','name','description').run(db.conn))
            create_dict['hardware'][m]=newlist
    return create_dict

