#
#   Copyright © 2022 Josep Maria Viñolas Auquer
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import logging
import os
import traceback
from datetime import datetime, timedelta

import jwt
import requests

from .exceptions import Error


class ApiClient:
    def __init__(self, service="api"):
        self.service = service
        if service == "api":
            subpath = "/api/v3"
        if service == "engine":
            subpath = ""
        api_domain = os.environ.get("API_DOMAIN", False)
        if api_domain:
            self.base_url = "https://" + api_domain + subpath
        else:
            self.base_url = "http://isard-" + service + ":5000" + subpath
        self.verifycert = False
        logging.info("Api base url to " + service + " set to " + self.base_url)

    def post(self, url, data={}):
        try:
            resp = requests.post(
                self.base_url + url,
                json=data,
                headers=self.header_auth(),
                verify=self.verifycert,
            )
            if resp.status_code == 200:
                return json.loads(resp.text)
            raise Error(
                "internal_server",
                "POST error "
                + str(resp.status_code)
                + " "
                + self.base_url
                + url
                + " : "
                + resp.text,
                traceback.format_exc(),
            )
        except:
            raise Error(
                "internal_server",
                "POST error "
                + str(resp.status_code)
                + " "
                + self.base_url
                + url
                + " : "
                + resp.text,
                traceback.format_exc(),
            )

    def get(self, url):
        try:
            resp = requests.get(
                self.base_url + url, headers=self.header_auth(), verify=self.verifycert
            )
            if resp.status_code == 200:
                return json.loads(resp.text)
            raise Error(
                "internal_server",
                "GET error "
                + str(resp.status_code)
                + " "
                + self.base_url
                + url
                + " : "
                + resp.text,
                traceback.format_exc(),
            )
        except:
            raise Error(
                "internal_server",
                "GET error "
                + str(resp.status_code)
                + " "
                + self.base_url
                + url
                + " : "
                + resp.text,
                traceback.format_exc(),
            )

    def delete(self, url):
        try:
            resp = requests.delete(
                self.base_url + url, headers=self.header_auth(), verify=self.verifycert
            )
            if resp.status_code == 200:
                return json.loads(resp.text)
            raise Error(
                "internal_server",
                "DELETE error "
                + str(resp.status_code)
                + " "
                + self.base_url
                + url
                + " : "
                + resp.text,
                traceback.format_exc(),
            )
        except:
            raise Error(
                "internal_server",
                "DELETE error "
                + str(resp.status_code)
                + " "
                + self.base_url
                + url
                + " : "
                + resp.text,
                traceback.format_exc(),
            )

    def put(self, url, data={}):
        try:
            resp = requests.put(
                self.base_url + url,
                json=data,
                headers=self.header_auth(),
                verify=self.verifycert,
            )
            if resp.status_code == 200:
                return json.loads(resp.text)
            raise Error(
                "internal_server",
                "PUT error "
                + str(resp.status_code)
                + " "
                + self.base_url
                + url
                + " : "
                + resp.text,
                traceback.format_exc(),
            )
        except:
            raise Error(
                "internal_server",
                "UPDATE error "
                + str(resp.status_code)
                + " "
                + self.base_url
                + url
                + " : "
                + resp.text,
                traceback.format_exc(),
            )

    def header_auth(self):
        token = jwt.encode(
            {
                "exp": datetime.utcnow() + timedelta(seconds=20),
                "kid": "isardvdi",
                "data": {
                    "role_id": "admin",
                    "user_id": "isard-scheduler",
                    "category_id": "*",
                },
            },
            os.environ["API_ISARDVDI_SECRET"],
            algorithm="HS256",
        )
        return {"Authorization": "Bearer " + token}
