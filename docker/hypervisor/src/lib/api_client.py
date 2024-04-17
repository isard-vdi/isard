import getpass
import json
import logging
import os
import time
import traceback
from datetime import datetime, timedelta

import jwt
import requests


class ApiClient:
    def __init__(self):
        api_domain = os.environ.get("API_DOMAIN", False)
        if api_domain and api_domain != "isard-api":
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
                "exp": datetime.utcnow() + timedelta(seconds=90),
                "kid": "isardvdi-hypervisors",
                "session_id": "isardvdi-service",
                "data": {
                    "role_id": "hypervisor",
                    "category_id": "default",
                },
            },
            os.environ["API_HYPERVISORS_SECRET"],
            algorithm="HS256",
        )
        return {"Authorization": "Bearer " + token}
