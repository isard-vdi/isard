#!/usr/bin/env python
# coding=utf-8
#
# Copyright 2017-2020 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

import traceback

from .._common.api_exceptions import Error
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..libv2.isardViewer import isardViewer

isardviewer = isardViewer()


class ApiXml:
    def __init__(self):
        None

    def VirtInstallGet(self, id):
        with app.app_context():
            virt_install = r.table("virt_install").get(id).run(db.conn)
        if virt_install is None:
            raise Error(
                "not_found",
                "Virt install xml not found",
                traceback.format_exc(),
            )
        return virt_install
