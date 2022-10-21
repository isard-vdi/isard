#!flask/bin/python
# coding=utf-8
#
# Copyright 2017-2020 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json

from api import app

from .._common.api_exceptions import Error
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_xml import ApiXml

xml = ApiXml()


@app.route("/api/v3/xml/virt_install/<id>", methods=["GET"])
def api_v3_xml_virt_install(id):
    data = xml.VirtInstallGet(id)
    return json.dumps(data), 200, {"Content-Type": "application/json"}
