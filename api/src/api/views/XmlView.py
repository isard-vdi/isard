#!flask/bin/python
# coding=utf-8
#
# Copyright 2017-2020 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from api import app
import traceback

from uuid import uuid4
import json
from flask import request
from ..libv2.apiv2_exc import *
from ..libv2.quotas_exc import *


def tsend(txt):
    None


from ..libv2.carbon import Carbon

carbon = Carbon()

from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_xml import ApiXml

xml = ApiXml()


@app.route("/api/v2/xml/virt_install/<id>", methods=["GET"])
def api_v2_xml_virt_install(id):
    try:
        data = xml.VirtInstallGet(id)
        return json.dumps(data), 200, {"ContentType": "application/json"}
    except XmlNotFound:
        return (
            json.dumps(
                {"code": 1, "msg": "VirtInstall " + id + " not exists in database"}
            ),
            404,
            {"ContentType": "application/json"},
        )

    except Exception:
        error = traceback.format_exc()
        return (
            json.dumps(
                {"code": 9, "msg": "VirtInstallGet general exception: " + error}
            ),
            500,
            {"ContentType": "application/json"},
        )
