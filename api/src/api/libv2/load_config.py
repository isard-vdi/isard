# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

# ~ from ..lib.log import *
# ~ import logging as cfglog

import logging as log

# ~ from .flask_rethink import RethinkDB
import os
import sys
import time
import traceback

import yaml
from cerberus import Validator, rules_set_registry, schema_registry
from rethinkdb import RethinkDB

from api import app

from .helpers import _parse_string

r = RethinkDB()


class IsardValidator(Validator):
    def _normalize_default_setter_genid(self, document):
        return _parse_string(document["name"])

    def _normalize_default_setter_genidlower(self, document):
        return _parse_string(document["name"]).lower()

    def _normalize_default_setter_gengroupid(self, document):
        return _parse_string(
            document["parent_category"] + "-" + document["uid"]
        ).lower()

    def _normalize_default_setter_genmediaid(self, document):
        return _parse_string("_" + document["user"] + "-" + document["name"])

    def _normalize_default_setter_genuserid(self, document):
        return _parse_string(
            document["provider"]
            + "-"
            + document["category"]
            + "-"
            + document["uid"]
            + "-"
            + document["username"]
        )

    def _normalize_default_setter_gendeploymentid(self, document):
        return _parse_string(document["uid"] + "=" + document["name"])

    def _normalize_default_setter_mediaicon(self, document):
        if document["kind"] == "iso":
            return _parse_string("fa-circle-o")
        else:
            return _parse_string("fa-floppy-o")

    def _check_with_validate_vlan(self, field, value):
        """
        Value should be a string with a numeric value >= 1 and <= 4094
        """
        if not (value.isnumeric() and 1 <= int(value) <= 4094):
            self._error(
                field, "Value should be a string with a numeric value >= 1 and <= 4094"
            )

    def _check_with_validate_vlan_range(self, field, value):
        """
        Value should be a string with a numeric range like 55-33 and range should be >= 1 and <= 4094
        """
        range = value.split("-")
        if len(range) != 2 or not range[0].isnumeric() or not range[1].isnumeric():
            self._error(
                field, 'Value should be a string with a numeric range like "55-33"'
            )
        elif int(range[0]) > int(range[1]):
            self._error(
                field, "Last range number cannot be less than first range number"
            )
        elif not 1 <= int(range[0]) <= 4094 or not 1 <= int(range[1]) <= 4094:
            self._error(field, "Range limits should be >= 1 and <= 4094")


def load_validators(purge_unknown=True):
    snippets_path = os.path.join(app.root_path, "schemas/snippets")
    for snippets_filename in os.listdir(snippets_path):
        with open(os.path.join(snippets_path, snippets_filename)) as file:
            snippet_schema_yml = file.read()
            snippet_schema = yaml.load(snippet_schema_yml, Loader=yaml.FullLoader)
            schema_registry.add(snippets_filename.split(".")[0], snippet_schema)

    validators = {}
    schema_path = os.path.join(app.root_path, "schemas")
    for schema_filename in os.listdir(schema_path):
        try:
            with open(os.path.join(schema_path, schema_filename)) as file:
                schema_yml = file.read()
                schema = yaml.load(schema_yml, Loader=yaml.FullLoader)
                validators[schema_filename.split(".")[0]] = IsardValidator(
                    schema, purge_unknown=purge_unknown
                )
        except IsADirectoryError:
            None
    return validators


app.validators = load_validators()


class loadConfig:
    def __init__(self, app=None):
        None

    def check_db(self):
        ready = False
        while not ready:
            try:
                conn = r.connect(
                    host=app.config["RETHINKDB_HOST"],
                    port=app.config["RETHINKDB_PORT"],
                    auth_key="",
                    db=app.config["RETHINKDB_DB"],
                )
                print("Database server OK")
                app.system_tables = r.table_list().run(conn)
                ready = True
            except Exception as e:
                # print(traceback.traceback.format_exc())
                print(
                    "Database server "
                    + app.config["RETHINKDB_HOST"]
                    + ":"
                    + app.config["RETHINKDB_PORT"]
                    + " not present. Waiting to be ready"
                )
                time.sleep(2)
        ready = False
        while not ready:
            try:
                tables = list(r.db("isard").table_list().run(conn))
            except:
                print("  No tables yet in database")
                time.sleep(1)
                continue
            if "config" in tables:
                ready = True
            else:
                print("Waiting for database to be populated with all tables...")
                print("   " + str(len(tables)) + " populated")
                time.sleep(2)

        secret = app.ram["secrets"]["isardvdi"] = os.environ["API_ISARDVDI_SECRET"]
        r.db("isard").table("secrets").insert(
            {
                "id": "isardvdi",
                "secret": secret,
                "description": "isardvdi",
                "domain": "localhost",
                "category_id": "default",
                "role_id": "admin",
            },
            conflict="replace",
        ).run(conn)
        secret = app.ram["secrets"]["isardvdi-hypervisors"] = os.environ[
            "API_HYPERVISORS_SECRET"
        ]
        r.db("isard").table("secrets").insert(
            {
                "id": "isardvdi-hypervisors",
                "secret": secret,
                "description": "isardvdi hypervisors access",
                "domain": "*",
                "category_id": "default",
                "role_id": "hypervisor",
            },
            conflict="replace",
        ).run(conn)

    def init_app(self, app):
        """
        Read RethinkDB configuration from environ
        """
        try:
            app.config.setdefault(
                "RETHINKDB_HOST", os.environ.get("RETHINKDB_HOST", "isard-db")
            )
            app.config.setdefault(
                "RETHINKDB_PORT", os.environ.get("RETHINKDB_PORT", "28015")
            )
            app.config.setdefault("RETHINKDB_AUTH", "")
            app.config.setdefault(
                "RETHINKDB_DB", os.environ.get("RETHINKDB_DB", "isard")
            )

            app.config.setdefault("LOG_LEVEL", os.environ.get("LOG_LEVEL", "INFO"))
            app.config.setdefault("LOG_FILE", "isard-api.log")
            app.debug = True if os.environ["LOG_LEVEL"] == "DEBUG" else False

        except:
            log.error(traceback.traceback.format_exc())
            log.error("Missing parameters!")
            print("Missing parameters!")
            return False
        print("Initial configuration loaded...")
        self.check_db()
        return True
