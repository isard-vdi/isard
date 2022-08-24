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
from datetime import datetime, timedelta

import requests
from jose import jwt


class ApiClient:
    def __init__(self):
        api_domain = os.environ.get("API_DOMAIN", False)
        if api_domain:
            self.base_url = "https://" + api_domain + "/api/v3/"
        else:
            self.base_url = "http://isard-api:5000/api/v3/"
        self.verifycert = False
        print("Api base url set to " + self.base_url)

    def post(self, url, data={}):
        try:
            logging.info("POST api url: " + self.base_url + url)
            resp = requests.post(
                self.base_url + url,
                data=data,
                headers=self.header_auth(),
                verify=self.verifycert,
            )
            if resp.status_code == 200:
                return json.loads(resp.text)
            logging.error("ERROR RESPONSE: " + resp.text)
            return False
        except:
            raise

    def get(self, url):
        try:
            resp = requests.get(
                self.base_url + url, headers=self.header_auth(), verify=self.verifycert
            )
            if resp.status_code == 200:
                return json.loads(resp.text)
            logging.error("ERROR RESPONSE: " + resp.text)
            return False
        except:
            raise

    def delete(self, url):
        try:
            resp = requests.delete(
                self.base_url + url, headers=self.header_auth(), verify=self.verifycert
            )
            if resp.status_code == 200:
                return json.loads(resp.text)
            logging.error("ERROR RESPONSE: " + resp.text)
            return False
        except:
            raise

    def update(self, url, data={}):
        try:
            logging.error("PUT api url: " + self.base_url + url)
            resp = requests.put(
                self.base_url + url,
                data=data,
                headers=self.header_auth(),
                verify=self.verifycert,
            )
            if resp.status_code == 200:
                return json.loads(resp.text)
            logging.error("ERROR RESPONSE: " + resp.text)
            return False
        except:
            raise

    def header_auth(self):
        token = jwt.encode(
            {
                "exp": datetime.utcnow() + timedelta(seconds=20),
                "kid": "isardvdi",
                "data": {
                    "role_id": "admin",
                    "category_id": "*",
                },
            },
            os.environ["API_ISARDVDI_SECRET"],
            algorithm="HS256",
        )
        return {"Authorization": "Bearer " + token}
