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

    def check(self, dict, action):
        # ~ These are the actions:
        # ~ {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
        if dict[action] or dict["unchanged"]:
            return True
        if not dict["errors"]:
            return True
        return False

    """
    ADMIN API
    """

    def get_group(self, id):
        with app.app_context():
            group = r.table("groups").get(id).run(db.conn)
        if group == None:
            return {}
        return group

    def get_admin_table(self, table, pluck=False, id=False, order=False, flatten=True):
        with app.app_context():
            if id and not pluck:
                data = r.table(table).get(id).run(db.conn)
                return self.f.flatten_dict(data) if flatten else data
            if pluck and not id:
                if order:
                    data = r.table(table).order_by(order).pluck(pluck).run(db.conn)
                    return self.f.table_values_bstrap(data) if flatten else list(data)
                else:
                    data = r.table(table).pluck(pluck).run(db.conn)
                    return self.f.table_values_bstrap(data) if flatten else list(data)
            if pluck and id:
                data = r.table(table).get(id).pluck(pluck).run(db.conn)
                return self.f.flatten_dict(data) if flatten else data
            if order:
                data = r.table(table).order_by(order).run(db.conn)
                return self.f.table_values_bstrap(data) if flatten else list(data)
            else:
                data = r.table(table).run(db.conn)
                return self.f.table_values_bstrap(data) if flatten else list(data)

    def get_admin_table_term(self, table, field, value, kind=False, pluck=False):
        with app.app_context():
            if kind:
                if pluck:
                    return self.f.table_values_bstrap(
                        r.table(table)
                        .get_all(kind, index="kind")
                        .filter(lambda doc: doc[field].match("(?i)" + value))
                        .pluck(pluck)
                        .run(db.conn)
                    )
                else:
                    return self.f.table_values_bstrap(
                        r.table(table)
                        .get_all(kind, index="kind")
                        .filter(lambda doc: doc[field].match("(?i)" + value))
                        .run(db.conn)
                    )
            else:
                if pluck:
                    return self.f.table_values_bstrap(
                        r.table(table)
                        .filter(lambda doc: doc[field].match("(?i)" + value))
                        .pluck(pluck)
                        .run(db.conn)
                    )
                else:
                    return self.f.table_values_bstrap(
                        r.table(table)
                        .filter(lambda doc: doc[field].match("(?i)" + value))
                        .run(db.conn)
                    )

    def insert_table_dict(self, table, dict):
        with app.app_context():
            return self.check(r.table(table).insert(dict).run(db.conn), "inserted")

    def update_table_dict(self, table, id, dict, keep_missing_fields=False):
        with app.app_context():
            if keep_missing_fields == True:
                old_dict = r.table(table).get(id).pluck(dict.keys()).run(db.conn)
                dict = self.merge_nested_dict(old_dict, dict)
            return self.check(
                r.table(table).get(id).update(dict).run(db.conn), "replaced"
            )

    """
    DOMAINS
    """

    # ~ def get_admin_domains(self,kind=False):
    # ~ with app.app_context():
    # ~ if not kind:
    # ~ return self.f.table_values_bstrap(r.table('domains').without('xml','hardware','create_dict').run(db.conn))
    # ~ else:
    # ~ return self.f.table_values_bstrap(r.table('domains').get_all(kind,index='kind').without('xml','hardware','create_dict').run(db.conn))

    def get_admin_domains_with_derivates(self, id=False, kind=False):
        with app.app_context():
            if kind == "template":
                if not id:
                    return list(
                        r.table("domains")
                        .get_all("template", index="kind")
                        .without("xml", "history_domain")
                        .merge(
                            lambda domain: {
                                "derivates": r.table("domains")
                                .filter(
                                    lambda derivates: derivates["parents"].contains(
                                        domain["id"]
                                    )
                                )
                                .count()
                                # ~ "derivates": r.table('domains').filter({'create_dict':{'origin':domain['id']}}).count()
                            }
                        )
                        .run(db.conn)
                    )
                if id:
                    return list(
                        r.table("domains")
                        .get(id)
                        .without("xml", "history_domain")
                        .merge(
                            lambda domain: {
                                "derivates": r.table("domains")
                                .filter(
                                    lambda derivates: derivates["parents"].contains(
                                        domain["id"]
                                    )
                                )
                                .count()
                                # ~ "derivates": r.table('domains').filter({'create_dict':{'origin':domain['id']}}).count()
                            }
                        )
                        .run(db.conn)
                    )
            else:
                return list(
                    r.table("domains")
                    .get_all(kind, index="kind")
                    .without("xml")
                    .merge(
                        lambda domain: {
                            "accessed": domain["history_domain"][0]["when"].default(0)
                        }
                    )
                    .run(db.conn)
                )

    def is_template_removable(self, tmpl_id, user_id):
        all_template_derivates = self.domain_derivates_count(tmpl_id)
        usr_template_derivates = self.domain_derivates_count(tmpl_id, user_id)
        if all_template_derivates != usr_template_derivates:
            # Thre are templates/isard-admin/desktops not owned by the user
            return False
        else:
            return True

    def domain_derivates_count(self, id=False, username=False):
        with app.app_context():
            if username == False:
                domains = [
                    {
                        "id": d["id"],
                        "origin": (
                            d["create_dict"]["origin"]
                            if "create_dict" in d and "origin" in d["create_dict"]
                            else None
                        ),
                    }
                    for d in list(
                        r.table("domains")
                        .pluck("id", {"create_dict": {"origin"}})
                        .run(db.conn)
                    )
                ]
            else:
                domains = [
                    {
                        "id": d["id"],
                        "origin": (
                            d["create_dict"]["origin"]
                            if "create_dict" in d and "origin" in d["create_dict"]
                            else None
                        ),
                    }
                    for d in list(
                        r.table("domains")
                        .get_all(username, index="user")
                        .pluck("id", "user", {"create_dict": {"origin"}})
                        .run(db.conn)
                    )
                ]

            return self.domain_recursive_count(id, domains) - 1

    def domain_recursive_count(self, id, domains):

        count = 1
        doms = [d for d in domains if d["origin"] == id]
        for dom in doms:
            count += self.domain_recursive_count(dom["id"], domains)
        return count

    """
    HYPERVISORS
    """

    def hypervisors_get(self, id=False):
        with app.app_context():
            if id:
                flat_dict_list = self.f.flatten_dict(
                    r.table("hypervisors")
                    .get(id)
                    .merge(
                        lambda hyp: {
                            "started_domains": r.table("domains")
                            .get_all("Started", index="status")
                            .filter({"hyp_started": hyp["id"]})
                            .count()
                        }
                    )
                    .run(db.conn)
                )
            else:
                flat_dict_list = self.f.table_values_bstrap(
                    r.table("hypervisors")
                    .merge(
                        lambda hyp: {
                            "started_domains": r.table("domains")
                            .get_all("Started", index="status")
                            .filter({"hyp_started": hyp["id"]})
                            .count()
                        }
                    )
                    .run(db.conn)
                )
        return flat_dict_list

    def hypervisors_pools_get(self, flat=True):
        with app.app_context():
            if flat:
                return self.f.table_values_bstrap(
                    r.table("hypervisors_pools").run(db.conn)
                )
            else:
                return list(r.table("hypervisors_pools").run(db.conn))

    def get_admin_config(self, id=None):
        with app.app_context():
            if id == None:
                return self.f.flatten_dict(r.table("config").get(1).run(db.conn))
            else:
                return self.f.flatten_dict(r.table("config").get(1).run(db.conn))

    """
    BACKUP & RESTORE
    """

    def backup_db(self):
        id = "isard_backup_" + datetime.now().strftime("%Y%m%d-%H%M%S")
        path = "./backups/"
        os.makedirs(path, exist_ok=True)
        with app.app_context():
            dict = {
                "id": id,
                "filename": id + ".tar.gz",
                "path": path,
                "description": "",
                "when": time.time(),
                "data": {},
                "status": "Initializing",
                "version": r.table("config")
                .get(1)
                .pluck("version")
                .run(db.conn)["version"],
            }
        with app.app_context():
            r.table("backups").insert(dict).run(db.conn)
        skip_tables = [
            "backups",
            "disk_operations",
        ]
        isard_db = {}
        with app.app_context():
            r.table("backups").get(id).update({"status": "Loading tables"}).run(db.conn)
            for table in r.table_list().run(db.conn):
                if table not in skip_tables:
                    isard_db[table] = list(r.table(table).run(db.conn))
                    dict["data"][table] = r.table(table).info().run(db.conn)
                    r.table("backups").get(id).update(
                        {"data": {table: r.table(table).count().run(db.conn)}}
                    ).run(db.conn)
        with app.app_context():
            dict = r.table("backups").get(id).run(db.conn)
            r.table("backups").get(id).update({"status": "Dumping to file"}).run(
                db.conn
            )
        with open(path + id + ".rethink", "wb") as isard_rethink_file:
            pickle.dump(dict, isard_rethink_file)
        with open(path + id + ".json", "wb") as isard_db_file:
            pickle.dump(isard_db, isard_db_file)
        with app.app_context():
            r.table("backups").get(id).update({"status": "Compressing"}).run(db.conn)
        with tarfile.open(path + id + ".tar.gz", "w:gz") as tar:
            tar.add(path + id + ".json", arcname=os.path.basename(path + id + ".json"))
            tar.add(
                path + id + ".rethink", arcname=os.path.basename(path + id + ".rethink")
            )
            tar.close()
        try:
            os.remove(path + id + ".json")
            os.remove(path + id + ".rethink")
        except OSError:
            pass
        with app.app_context():
            r.table("backups").get(id).update({"status": "Finished creating"}).run(
                db.conn
            )

    def recreate_table(self, tbl_data):
        if not r.table_list().contains(tbl_data["name"]).run(db.conn):
            log.info("Restoring table {}".format(k))
            r.table_create(tbl_data["name"], primary_key=tbl_data["primary_key"]).run(
                db.conn
            )
            for idx in tbl_data["indexes"]:
                r.table(tbl_data["name"]).index_create(idx).run(db.conn)
                r.table(tbl_data["name"]).index_wait(idx).run(db.conn)
                log.info("Created index: {}".format(idx))

    def restore_db(self, id):
        with app.app_context():
            dict = r.table("backups").get(id).run(db.conn)
            r.table("backups").get(id).update({"status": "Uncompressing backup"}).run(
                db.conn
            )
        path = dict["path"]
        with tarfile.open(path + id + ".tar.gz", "r:gz") as tar:
            tar.extractall(path)
            tar.close()
        with app.app_context():
            r.table("backups").get(id).update({"status": "Loading data.."}).run(db.conn)
        with open(path + id + ".rethink", "rb") as tbl_data_file:
            tbl_data = pickle.load(tbl_data_file)
        with open(path + id + ".json", "rb") as isard_db_file:
            isard_db = pickle.load(isard_db_file)
        for k, v in isard_db.items():
            with app.app_context():
                try:
                    self.recreate_table(tbl_data[k])
                except Exception as e:
                    pass
                if not r.table_list().contains(k).run(db.conn):
                    log.error(
                        "Table {} not found, should have been created on IsardVDI startup.".format(
                            k
                        )
                    )
                    continue
                    # ~ return False
                else:
                    log.info("Restoring table {}".format(k))
                    with app.app_context():
                        r.table("backups").get(id).update(
                            {"status": "Updating table: " + k}
                        ).run(db.conn)
                    # Avoid updating admin user!
                    if k == "users":
                        v[:] = [u for u in v if u.get("id") != "admin"]
                    log.info(r.table(k).insert(v, conflict="update").run(db.conn))
        with app.app_context():
            r.table("backups").get(id).update({"status": "Finished restoring"}).run(
                db.conn
            )
        try:
            os.remove(path + id + ".json")
            os.remove(path + id + ".rethink")
        except OSError as e:
            log.error(e)
            pass

    def download_backup(self, id):
        with app.app_context():
            dict = r.table("backups").get(id).run(db.conn)
        with open(dict["path"] + dict["filename"], "rb") as isard_db_file:
            return dict["path"], dict["filename"], isard_db_file.read()

    def info_backup_db(self, id):
        with app.app_context():
            dict = r.table("backups").get(id).run(db.conn)
            # ~ r.table('backups').get(id).update({'status':'Uncompressing backup'}).run(db.conn)
        path = dict["path"]
        with tarfile.open(path + id + ".tar.gz", "r:gz") as tar:
            tar.extractall(path)
            tar.close()
        # ~ with app.app_context():
        # ~ r.table('backups').get(id).update({'status':'Loading data..'}).run(db.conn)
        with open(path + id + ".rethink", "rb") as tbl_data_file:
            tbl_data = pickle.load(tbl_data_file)
        with open(path + id + ".json", "rb") as isard_db_file:
            isard_db = pickle.load(isard_db_file)
        i = 0
        for sch in isard_db["scheduler_jobs"]:
            isard_db["scheduler_jobs"][i].pop("job_state", None)
            i = i + 1
        # ~ i=0
        # ~ for sch in isard_db['users']:
        # ~ isard_db['users'][i].pop('password',None)
        # ~ i=i+1
        try:
            os.remove(path + id + ".json")
            os.remove(path + id + ".rethink")
        except OSError as e:
            log.error(e)
            pass
        return tbl_data, isard_db

    def check_new_values(self, table, new_data):
        backup = new_data
        dbb = list(r.table(table).run(db.conn))
        result = []
        for b in backup:
            found = False
            for d in dbb:
                if d["id"] == b["id"]:
                    found = True
                    b["new_backup_data"] = False
                    result.append(b)
                    break
            if not found:
                b["new_backup_data"] = True
                result.append(b)
        return result

    def upload_backup(self, handler):
        path = "./backups/"
        id = handler.filename.split(".tar.gz")[0]
        filename = secure_filename(handler.filename)
        handler.save(os.path.join(path + filename))
        # ~ with app.app_context():
        # ~ dict=r.table('backups').get(id).run(db.conn)
        # ~ r.table('backups').get(id).update({'status':'Uncompressing backup'}).run(db.conn)
        # ~ path=dict['path']

        with tarfile.open(path + handler.filename, "r:gz") as tar:
            tar.extractall(path)
            tar.close()
        # ~ with app.app_context():
        # ~ r.table('backups').get(id).update({'status':'Loading data..'}).run(db.conn)
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

    def remove_backup_db(self, id):
        with app.app_context():
            dict = r.table("backups").get(id).run(db.conn)
        path = dict["path"]
        try:
            os.remove(path + id + ".tar.gz")
        except OSError:
            pass
        with app.app_context():
            r.table("backups").get(id).delete().run(db.conn)

    """
    VIRT-BUILDER VIRT-INSTALL
    """

    def merge_nested_dict(self, old, new):
        for k, v in new.items():
            if k in old and isinstance(old[k], dict) and isinstance(new[k], Mapping):
                self.merge_nested_dict(old[k], new[k])
            else:
                old[k] = new[k]
        return old

    """
    JUMPERURL
    """

    def get_jumperurl(self, id):
        with app.app_context():
            domain = r.table("domains").get(id).run(db.conn)
        if domain == None:
            return {}
        if "jumperurl" not in domain.keys():
            return {"jumperurl": False}
        return {"jumperurl": domain["jumperurl"]}

    def jumperurl_reset(self, id, disabled=False, length=32):
        if disabled == True:
            with app.app_context():
                r.table("domains").get(id).update({"jumperurl": False}).run(db.conn)
            return True

        code = self.jumperurl_gencode()
        with app.app_context():
            r.table("domains").get(id).update({"jumperurl": code}).run(db.conn)
        return code

    def jumperurl_gencode(self, length=32):
        code = False
        while code == False:
            code = secrets.token_urlsafe(length)
            found = list(
                r.table("domains").get_all(code, index="jumperurl").run(db.conn)
            )
            if len(found) == 0:
                return code
        return False


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
