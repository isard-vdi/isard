#!flask/bin/python
# coding=utf-8
#
# Copyright 2017-2020 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import traceback
from uuid import uuid4

from flask import request

from api import app

from ..libv2.apiv2_exc import *
from ..libv2.quotas import Quotas
from ..libv2.quotas_exc import *

quotas = Quotas()

from ..libv2.api_xml import ApiXml

xml = ApiXml()


@app.route("/api/v3/xml/virt_install/<id>", methods=["GET"])
def api_v3_xml_virt_install(id):
    try:
        data = xml.VirtInstallGet(id)
        return json.dumps(data), 200, {"Content-Type": "application/json"}
    except XmlNotFound:
        return (
            json.dumps(
                {"code": 1, "msg": "VirtInstall " + id + " not exists in database"}
            ),
            404,
            {"Content-Type": "application/json"},
        )

    except Exception:
        error = traceback.format_exc()
        return (
            json.dumps(
                {"code": 9, "msg": "VirtInstallGet general exception: " + error}
            ),
            500,
            {"Content-Type": "application/json"},
        )
