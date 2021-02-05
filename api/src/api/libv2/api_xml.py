#!/usr/bin/env python
# coding=utf-8
#
# Copyright 2017-2020 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
from api import app

from rethinkdb import RethinkDB

r = RethinkDB()


from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..libv2.isardViewer import isardViewer

isardviewer = isardViewer()

from .apiv2_exc import XmlNotFound

from .ds import DS

ds = DS()


class ApiXml:
    def __init__(self):
        None

    def VirtInstallGet(self, id):
        with app.app_context():
            virt_install = r.table("virt_install").get(id).run(db.conn)
        if virt_install is None:
            raise XmlNotFound
        return virt_install
