# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import os
import pickle
import random
import socket
import tarfile

#!/usr/bin/env python
# coding=utf-8
import time
import traceback
from contextlib import closing
from datetime import datetime, timedelta
from string import ascii_lowercase, digits

import pem
import requests
import rethinkdb as r
from OpenSSL import crypto
from werkzeug.utils import secure_filename

from webapp import app

from ..lib.log import *
from .flask_rethink import RethinkDB

db = RethinkDB(app)
db.init_app(app)

from .api_client import ApiClient
from .isardViewer import default_guest_properties

apic = ApiClient()

import csv
import io
import secrets
from collections import Mapping, defaultdict

from ..auth.authentication import Password
from .ds import DS

ds = DS()


class isardAdmin:
    def __init__(self):
        self.f = flatten()

    def get_admin_config(self, id=None):
        with app.app_context():
            if id == None:
                return self.f.flatten_dict(r.table("config").get(1).run(db.conn))
            else:
                return self.f.flatten_dict(r.table("config").get(1).run(db.conn))

    def upload_backup(self, handler):
        path = "./backups/"
        id = handler.filename.split(".tar.gz")[0]
        filename = secure_filename(handler.filename)
        handler.save(os.path.join(path + filename))

        with tarfile.open(path + handler.filename, "r:gz") as tar:
            def is_within_directory(directory, target):
                
                abs_directory = os.path.abspath(directory)
                abs_target = os.path.abspath(target)
            
                prefix = os.path.commonprefix([abs_directory, abs_target])
                
                return prefix == abs_directory
            
            def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
            
                for member in tar.getmembers():
                    member_path = os.path.join(path, member.name)
                    if not is_within_directory(path, member_path):
                        raise Exception("Attempted Path Traversal in Tar File")
            
                tar.extractall(path, members, numeric_owner=numeric_owner) 
                
            
            safe_extract(tar, path)
            tar.close()
        with open(path + id + ".rethink", "rb") as isard_rethink_file:
            isard_rethink = pickle.load(isard_rethink_file)
        with app.app_context():
            log.info(
                r.table("backups").insert(isard_rethink, conflict="update").run(db.conn)
            )
        with app.app_context():
            r.table("backups").get(id).update({"status": "Finished uploading"}).run(
                db.conn
            )
        try:
            os.remove(path + id + ".json")
            os.remove(path + id + ".rethink")
        except OSError as e:
            log.error(e)
            pass


"""
FLATTEN AND UNFLATTEN DICTS
"""


class flatten(object):
    def __init__(self):
        None

    def table_header_bstrap(self, table, pluck=None, editable=False):
        columns = []
        for key, value in list(self.flatten_table_keys(table, pluck).items()):
            if editable and key != "id":
                columns.append(
                    {"field": key, "title": key, "sortable": True, "editable": True}
                )
            else:
                columns.append({"field": key, "title": key})
        return columns

    def table_values_bstrap(self, rethink_cursor):
        data_in = list(rethink_cursor)
        data_out = []
        for d in data_in:
            data_out.append(self.flatten_dict(d))
        return data_out

    def flatten_table_keys(self, table, pluck=None):
        with app.app_context():
            if pluck != None:
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

    def flatten_dict(self, d):
        def items():
            for key, value in list(d.items()):
                if isinstance(value, dict):
                    for subkey, subvalue in list(self.flatten_dict(value).items()):
                        yield key + "-" + subkey, subvalue
                else:
                    yield key, value

        return dict(items())

    def unflatten_dict(self, dictionary):
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
