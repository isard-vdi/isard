# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import os
import pickle
import tarfile

import rethinkdb as r
from werkzeug.utils import secure_filename

from webapp import app

from ..lib.log import *
from .flask_rethink import RethinkDB

db = RethinkDB(app)
db.init_app(app)

from flask_login import current_user


def get_login_path():
    with app.app_context():
        category = (
            r.table("categories")
            .get(current_user.category)
            .pluck("id", "name", "frontend", "custom_url_name")
            .run(db.conn)
        )
    if category.get("frontend", False):
        return "/login/"
    else:
        return "/login/" + category.get("custom_url_name")


def upload_backup(handler):
    path = "./backups/"
    id = handler.filename.split(".tar.gz")[0]
    filename = secure_filename(handler.filename)
    handler.save(os.path.join(path + filename))

    with tarfile.open(path + handler.filename, "r:gz") as tar:
        tar.extractall(path)
        tar.close()
    with open(path + id + ".rethink", "rb") as isard_rethink_file:
        isard_rethink = pickle.load(isard_rethink_file)
    with app.app_context():
        log.info(
            r.table("backups").insert(isard_rethink, conflict="update").run(db.conn)
        )
    with app.app_context():
        r.table("backups").get(id).update({"status": "Finished uploading"}).run(db.conn)
    try:
        os.remove(path + id + ".json")
        os.remove(path + id + ".rethink")
    except OSError as e:
        log.error(e)
        pass


class isardAdmin:
    def __init__(self):
        self.f = flatten()

    def get_admin_config(self, id=None):
        with app.app_context():
            if id == None:
                return self.f.flatten_dict(r.table("config").get(1).run(db.conn))
            else:
                return self.f.flatten_dict(r.table("config").get(1).run(db.conn))


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
