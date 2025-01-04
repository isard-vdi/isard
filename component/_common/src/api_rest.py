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
import time
import traceback
from datetime import datetime, timedelta

import jwt
import requests


def header_auth(service):
    token = jwt.encode(
        {
            "exp": datetime.utcnow() + timedelta(seconds=20),
            "kid": "isardvdi",
            "session_id": "isardvdi-service",
            "data": {"role_id": "admin", "category_id": "*", "user_id": service},
        },
        os.environ["API_ISARDVDI_SECRET"],
        algorithm="HS256",
    )
    return {"Authorization": "Bearer " + token}


def is_ip(ip):
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        for x in parts:
            if not x.isdigit():
                return False
            i = int(x)
            if i < 0 or i > 255:
                return False
    except:
        return False
    return True


container_base_path = {
    "isard-api": "/api/v3",
    "isard-scheduler": "/scheduler",
    "isard-notifier": "/notifier",
    "isard-authentication": "/authentication",
}


class ApiRest:
    def __init__(self, service="isard-api", base_url=None):
        if base_url:
            self.base_url = base_url
            self.verify_cert = False if base_url.startswith("http://") else True
        else:
            if service == "isard-api":
                actual_server = os.environ.get("API_DOMAIN")
            if service == "isard-scheduler":
                actual_server = "isard-scheduler"
            if service == "isard-notifier":
                actual_server = "isard-notifier"
            if service == "isard-authentication":
                actual_server = "isard-authentication"
            if actual_server:
                if actual_server == "isard-authentication":
                    self.base_url = (
                        "http://"
                        + actual_server
                        + ":1313"
                        + container_base_path[service]
                    )
                    self.verify_cert = False
                elif actual_server == "localhost" or actual_server.startswith("isard-"):
                    self.base_url = (
                        "http://"
                        + actual_server
                        + ":5000"
                        + container_base_path[service]
                    )
                    self.verify_cert = False
                else:
                    self.base_url = (
                        "https://" + actual_server + container_base_path[service]
                    )
                    self.verify_cert = False if is_ip(actual_server) else True
            else:
                self.base_url = (
                    "http://" + service + ":5000" + container_base_path[service]
                )
                self.verify_cert = False
        self.service = service
        logging.debug(
            "Api base url for service " + service + " set to " + self.base_url
        )

    def wait_for(self, max_retries=-1, timeout=1):
        while max_retries:
            try:
                logging.info(
                    "Check connection to "
                    + self.service
                    + " container at "
                    + self.base_url
                )
                self.get()
                max_retries = 0
            except requests.exceptions.ConnectionError:
                logging.error(
                    "Unable to reach "
                    + self.service
                    + " container at "
                    + self.base_url
                    + " (ConnectionError)"
                )
                time.sleep(timeout)
                if max_retries >= 0:
                    max_retries -= 1
            except:
                logging.error(traceback.format_exc())
                logging.error(
                    "Unable to reach " + self.service + " container at " + self.base_url
                )
                time.sleep(timeout)
                if max_retries >= 0:
                    max_retries -= 1

    def get(self, url="", timeout=30):
        resp = requests.get(
            self.base_url + url,
            headers=header_auth(self.service),
            verify=self.verify_cert,
            timeout=timeout,
        )
        resp.raise_for_status()
        return json.loads(resp.text)

    def post(self, url, data={}, timeout=30):
        resp = requests.post(
            self.base_url + url,
            json=data,
            headers=header_auth(self.service),
            verify=self.verify_cert,
            timeout=timeout,
        )
        resp.raise_for_status()
        return json.loads(resp.text)

    def put(self, url, data={}, timeout=30):
        resp = requests.put(
            self.base_url + url,
            json=data,
            headers=header_auth(self.service),
            verify=self.verify_cert,
            timeout=timeout,
        )
        resp.raise_for_status()
        return json.loads(resp.text)

    def delete(self, url, data={}, timeout=30):
        resp = requests.delete(
            self.base_url + url,
            json=data,
            headers=header_auth(self.service),
            verify=self.verify_cert,
            timeout=timeout,
        )
        resp.raise_for_status()
        return json.loads(resp.text)
