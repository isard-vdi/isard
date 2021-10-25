import json
import os
import secrets
import time
import traceback
from datetime import datetime, timedelta
from pprint import pprint

from jose import jwt
from rethinkdb import r

domain = "localhost"
verifycert = False
## End set global vars

import unittest

import requests
import responses

# Users, so also desktops (one for each user)
items_to_create = 1
# download_desktop="slax93"
# download_desktop="zxspectrum"
download_desktop = "tetros"


class TestSimulate(unittest.TestCase):

    auths = {}
    dbconn = None
    base = "http://localhost:5000/api/v3"

    @classmethod
    def setUpClass(cls):
        cls.dbconn = r.connect("isard-db", 28015).repl()
        admin_secret_data = r.db("isard").table("secrets").get("isardvdi").run()
        admin_jwt = jwt.encode(
            {
                "exp": datetime.utcnow() + timedelta(hours=4),
                "kid": admin_secret_data["id"],
                "data": {
                    "role_id": admin_secret_data["role_id"],
                    "category_id": admin_secret_data["category_id"],
                },
            },
            admin_secret_data["secret"],
            algorithm="HS256",
        )
        cls.auths["isardvdi"] = {
            "secret": admin_secret_data,
            "jwt": admin_jwt,
            "header": {"Authorization": "Bearer " + admin_jwt},
        }

        manager_secret = secrets.token_urlsafe(32)
        manager_secret_data = {
            "id": "API_TESTS_CATEGORY_NAME",
            "secret": manager_secret,
            "description": "API_TESTS_CATEGORY_DESCRIPTION",
            "domain": "localhost",
            "category_id": "API_TESTS_CATEGORY_NAME",
            "role_id": "manager",
        }
        r.db("isard").table("secrets").insert(manager_secret_data).run()
        manager_jwt = jwt.encode(
            {
                "exp": datetime.utcnow() + timedelta(hours=4),
                "kid": manager_secret_data["id"],
                "data": {
                    "role_id": manager_secret_data["role_id"],
                    "category_id": manager_secret_data["category_id"],
                },
            },
            manager_secret_data["secret"],
            algorithm="HS256",
        )
        cls.auths["manager"] = {
            "secret": manager_secret,
            "jwt": manager_jwt,
            "header": {"Authorization": "Bearer " + manager_secret},
        }

    @classmethod
    def tearDownClass(cls):
        r.db("isard").table("secrets").get("API_TESTS_CATEGORY_NAME").delete().run()
        cls.dbconn.close()
        cls.auths = None

    def test_010_login(self):
        data = {"usr": "admin", "pwd": "IsardVDI"}
        category_id = "default"
        provider = "local"
        response = requests.post(
            self.base + "/login/" + category_id + "?provider=" + provider,
            data=data,
            verify=False,
        )
        # {'id':'local-default-admin-admin', 'jwt':'XXXXXXXXXXXX'}
        self.assertEqual(200, response.status_code)

    def test_020_admin_secret_correct(self):
        admin_secret = (
            r.db("isard")
            .table("secrets")
            .get("isardvdi")
            .pluck("secret")
            .run()["secret"]
        )
        self.assertEqual(admin_secret, os.environ["API_ISARDVDI_SECRET"])
        # self.auths['isardvdi']={'secret':admin_secret,
        #                         'header':{'Authorization': 'Bearer ' + admin_secret}}

    def test_030_admin_get_jwt_self(self):
        response = requests.get(
            self.base + "/admin/jwt/local-default-admin-admin",
            headers=self.auths["isardvdi"]["header"],
            verify=False,
        )
        self.assertEqual(200, response.status_code)

    def test_040_admin_add_category(self):
        category = {
            "category_name": "API TESTS CATEGORY NAME",
            "description": "API TESTS DESCRIPTION",
            "group_name": "API TESTS GROUP NAME",
            "frontend": False,
        }
        response = requests.post(
            self.base + "/admin/category",
            data=category,
            headers=self.auths["isardvdi"]["header"],
            verify=False,
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(json.loads(response.text)["id"], "API_TESTS_CATEGORY_NAME")

    def test_050_admin_get_categories(self):
        response = requests.get(
            self.base + "/admin/categories",
            headers=self.auths["isardvdi"]["header"],
            verify=False,
        )
        self.assertEqual(200, response.status_code)

        category = [
            c["id"]
            for c in json.loads(response.text)
            if c["id"] == "API_TESTS_CATEGORY_NAME"
        ]
        self.assertEqual(category[0], "API_TESTS_CATEGORY_NAME")

    def test_060_admin_get_group(self):
        response = requests.get(
            self.base + "/admin/groups",
            headers=self.auths["isardvdi"]["header"],
            verify=False,
        )

        self.assertEqual(200, response.status_code)

        group = [
            g["id"]
            for g in json.loads(response.text)
            if g["parent_category"] == "API_TESTS_CATEGORY_NAME"
        ]
        self.assertEqual(group[0], "API_TESTS_CATEGORY_NAME-API_TESTS_GROUP_NAME")

    def test_070_admin_add_users(self):
        for i in range(1, items_to_create + 1):
            data = {
                "provider": "local",
                "user_uid": "API_TEST_UID_" + str(i),
                "user_username": "API_TEST_USERNAME_" + str(i),
                "name": "API TEST NAME " + str(i),
                "role_id": "user",
                "category_id": "API_TESTS_CATEGORY_NAME",
                "group_id": "API_TESTS_CATEGORY_NAME-API_TESTS_GROUP_NAME",
                "password": "P@55s0rd",
            }
            response = requests.post(
                self.base + "/admin/user",
                data=data,
                headers=self.auths["isardvdi"]["header"],
                verify=False,
            )
            self.assertEqual(200, response.status_code)
            self.assertEqual(
                json.loads(response.text)["id"],
                "local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i),
            )

    def test_080_admin_get_users_jwt(self):
        for i in range(1, items_to_create + 1):
            response = requests.get(
                self.base
                + "/admin/jwt/local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i),
                headers=self.auths["isardvdi"]["header"],
                verify=False,
            )
            self.assertEqual(200, response.status_code)

    def test_090_admin_download_desktop(self):
        response = requests.get(
            self.base + "/admin/jwt/local-default-admin-admin",
            headers=self.auths["isardvdi"]["header"],
            verify=False,
        )
        self.assertEqual(200, response.status_code)
        jwt = json.loads(response.text)["jwt"]

        response = requests.get(
            self.base + "/admin/downloads/desktops",
            headers={"Authorization": "Bearer " + jwt},
            verify=False,
        )
        self.assertEqual(200, response.status_code)

        for dom in json.loads(response.text):
            if dom["id"].endswith(download_desktop):
                response = requests.post(
                    self.base + "/admin/downloads/desktop/" + dom["id"],
                    headers={"Authorization": "Bearer " + jwt},
                    verify=False,
                )
                self.assertEqual(200, response.status_code)
                desktop_id = dom["id"]

        loop = 0
        while loop <= 60:
            if (
                "Stopped"
                == r.db("isard")
                .table("domains")
                .get(desktop_id)
                .pluck("status")
                .run()["status"]
            ):
                self.assertTrue(True)
                break
            time.sleep(1)
            loop += 1
        if loop > 60:
            self.assertTrue(False)

    def test_100_admin_add_template(self):
        response = requests.get(
            self.base + "/admin/jwt/local-default-admin-admin",
            headers=self.auths["isardvdi"]["header"],
            verify=False,
        )
        self.assertEqual(200, response.status_code)
        jwt = json.loads(response.text)["jwt"]

        response = requests.get(
            self.base + "/admin/downloads/desktops",
            headers={"Authorization": "Bearer " + jwt},
            verify=False,
        )
        self.assertEqual(200, response.status_code)

        for dom in json.loads(response.text):
            if dom["id"].endswith(download_desktop):
                desktop_id = dom["id"]

        data = {
            "template_name": "API TEST TEMPLATE",
            "desktop_id": desktop_id,
            "allowed_groups": ["API_TESTS_CATEGORY_NAME-API_TESTS_GROUP_NAME"],
        }
        # Check if exists
        response = requests.get(
            self.base + "/template/_local-default-admin-admin-API_TEST_TEMPLATE",
            headers={"Authorization": "Bearer " + jwt},
            verify=False,
        )
        if response.status_code != 200:
            # Create
            response = requests.post(
                self.base + "/template",
                data=data,
                headers={"Authorization": "Bearer " + jwt},
                verify=False,
            )
            self.assertEqual(200, response.status_code)
            self.assertEqual(
                json.loads(response.text)["id"],
                "_local-default-admin-admin-API_TEST_TEMPLATE",
            )

        loop = 0
        while loop <= 15:
            response = requests.get(
                self.base + "/template/_local-default-admin-admin-API_TEST_TEMPLATE",
                headers={"Authorization": "Bearer " + jwt},
                verify=False,
            )
            if response.status_code == 200:
                self.assertTrue(True)
                break
            time.sleep(1)
            loop += 1
        if loop > 15:
            self.assertTrue(False)

    # def test_9_template(self):
    #     response = requests.get(self.base+'/admin/jwt/local-default-admin-admin',
    #                             headers=self.auths['isardvdi']['header'],
    #                             verify=False)
    #     self.assertEqual(200, response.status_code)
    #     jwt=json.loads(response.text)['jwt']

    #     data = {'template_name': 'template a6',
    #             'desktop_id': '_local-default-admin-admin_downloaded_slax93',
    #             'allowed_roles':['admin']}
    #     response = requests.post(self.base+'/template',
    #                             data=data,
    #                             headers={'Authorization': 'Bearer ' + jwt},
    #                             verify=False)
    #     self.assertEqual(200, response.status_code)

    def test_110_admin_add_desktops(self):
        for i in range(1, items_to_create + 1):
            response = requests.get(
                self.base
                + "/admin/jwt/local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i),
                headers=self.auths["isardvdi"]["header"],
                verify=False,
            )
            self.assertEqual(200, response.status_code)
            jwt = json.loads(response.text)["jwt"]

            data = {
                "desktop_name": "API_TESTS_DESKTOP",
                "template_id": "_local-default-admin-admin-API_TEST_TEMPLATE",
            }
            response = requests.post(
                self.base + "/persistent_desktop",
                data=data,
                headers={"Authorization": "Bearer " + jwt},
                verify=False,
            )
            self.assertTrue(
                200 == response.status_code or 3 == json.loads(response.text)["code"]
            )

            stopped = 0
            while stopped <= 10:
                response = requests.get(
                    self.base
                    + "/user/desktop/_local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                    + str(i)
                    + "-API_TEST_USERNAME_"
                    + str(i)
                    + "-API_TESTS_DESKTOP",
                    headers={"Authorization": "Bearer " + jwt},
                    verify=False,
                )
                self.assertEqual(200, response.status_code)

                if json.loads(response.text)["state"] != "Stopped":
                    stopped += 1
                    time.sleep(1)
                else:
                    self.assertTrue(True)
                    break
            if stopped > 10:
                self.assertTrue(False)

    def test_120_admin_start_desktops(self):
        for i in range(1, items_to_create + 1):
            response = requests.get(
                self.base
                + "/admin/jwt/local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i),
                headers=self.auths["isardvdi"]["header"],
                verify=False,
            )
            self.assertEqual(200, response.status_code)
            jwt = json.loads(response.text)["jwt"]

            response = requests.get(
                self.base
                + "/desktop/start/_local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i)
                + "-API_TESTS_DESKTOP",
                headers={"Authorization": "Bearer " + jwt},
                verify=False,
            )
            self.assertEqual(200, response.status_code)

            started = 0
            while started <= 10:
                response = requests.get(
                    self.base
                    + "/user/desktop/_local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                    + str(i)
                    + "-API_TEST_USERNAME_"
                    + str(i)
                    + "-API_TESTS_DESKTOP",
                    headers={"Authorization": "Bearer " + jwt},
                    verify=False,
                )
                self.assertEqual(200, response.status_code)

                if json.loads(response.text)["state"] != "Started":
                    started += 1
                    time.sleep(1)
                else:
                    self.assertTrue(True)
                    break
            if started > 10:
                self.assertTrue(False)

    def test_130_get_viewers(self):
        for i in range(1, items_to_create + 1):
            response = requests.get(
                self.base
                + "/admin/jwt/local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i),
                headers=self.auths["isardvdi"]["header"],
                verify=False,
            )
            self.assertEqual(200, response.status_code)
            jwt = json.loads(response.text)["jwt"]

            response = requests.get(
                self.base
                + "/user/desktop/_local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i)
                + "-API_TESTS_DESKTOP",
                headers={"Authorization": "Bearer " + jwt},
                verify=False,
            )
            self.assertEqual(200, response.status_code)
            self.assertEqual(
                json.loads(response.text)["viewers"], ["file-spice", "browser-vnc"]
            )

            response = requests.get(
                self.base
                + "/desktop/_local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i)
                + "-API_TESTS_DESKTOP/viewer/browser-vnc",
                headers={"Authorization": "Bearer " + jwt},
                verify=False,
            )
            self.assertEqual(200, response.status_code)
            pprint(json.loads(response.text))

            response = requests.get(
                self.base
                + "/desktop/_local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i)
                + "-API_TESTS_DESKTOP/viewer/file-spice",
                headers={"Authorization": "Bearer " + jwt},
                verify=False,
            )
            self.assertEqual(200, response.status_code)
            pprint(json.loads(response.text))

    def test_140_admin_stop_desktops(self):
        for i in range(1, items_to_create + 1):
            response = requests.get(
                self.base
                + "/admin/jwt/local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i),
                headers=self.auths["isardvdi"]["header"],
                verify=False,
            )
            self.assertEqual(200, response.status_code)
            jwt = json.loads(response.text)["jwt"]

            response = requests.get(
                self.base
                + "/desktop/stop/_local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i)
                + "-API_TESTS_DESKTOP",
                headers={"Authorization": "Bearer " + jwt},
                verify=False,
            )
            self.assertEqual(200, response.status_code)

            stopped = 0
            while stopped <= 40:
                response = requests.get(
                    self.base
                    + "/user/desktop/_local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                    + str(i)
                    + "-API_TEST_USERNAME_"
                    + str(i)
                    + "-API_TESTS_DESKTOP",
                    headers={"Authorization": "Bearer " + jwt},
                    verify=False,
                )
                self.assertEqual(200, response.status_code)

                if json.loads(response.text)["state"] != "Stopped":
                    stopped += 1
                    time.sleep(1)
                else:
                    self.assertTrue(True)
                    break
            if stopped > 40:
                self.assertTrue(False)

    def test_150_admin_delete_desktops(self):
        for i in range(1, items_to_create + 1):
            response = requests.get(
                self.base
                + "/admin/jwt/local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i),
                headers=self.auths["isardvdi"]["header"],
                verify=False,
            )
            self.assertEqual(200, response.status_code)
            jwt = json.loads(response.text)["jwt"]

            response = requests.delete(
                self.base
                + "/desktop/_local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i)
                + "-API_TESTS_DESKTOP",
                headers={"Authorization": "Bearer " + jwt},
                verify=False,
            )
            self.assertEqual(200, response.status_code)

            deleted = 0
            while deleted <= 10:
                response = requests.get(
                    self.base
                    + "/user/desktop/_local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                    + str(i)
                    + "-API_TEST_USERNAME_"
                    + str(i)
                    + "-API_TESTS_DESKTOP",
                    headers={"Authorization": "Bearer " + jwt},
                    verify=False,
                )
                if json.loads(response.text)["code"] != 3:
                    deleted += 1
                    time.sleep(1)
                else:
                    self.assertTrue(True)
                    break
            if deleted > 10:
                self.assertTrue(False)

        response = requests.get(
            self.base + "/admin/jwt/local-default-admin-admin",
            headers=self.auths["isardvdi"]["header"],
            verify=False,
        )
        self.assertEqual(200, response.status_code)
        jwt = json.loads(response.text)["jwt"]

        response = requests.get(
            self.base + "/user/desktops",
            headers={"Authorization": "Bearer " + jwt},
            verify=False,
        )
        result = (
            True
            if "_local-default-admin-admin_downloaded_" + download_desktop
            in [r["id"] for r in json.loads(response.text)][0]
            else False
        )
        self.assertTrue(result)

        response = requests.delete(
            self.base
            + "/desktop/_local-default-admin-admin_downloaded_"
            + download_desktop,
            headers={"Authorization": "Bearer " + jwt},
            verify=False,
        )
        self.assertEqual(200, response.status_code)

    def test_160_admin_delete_users(self):
        for i in range(1, items_to_create + 1):
            response = requests.delete(
                self.base
                + "/admin/user/local-API_TESTS_CATEGORY_NAME-API_TEST_UID_"
                + str(i)
                + "-API_TEST_USERNAME_"
                + str(i),
                headers=self.auths["isardvdi"]["header"],
                verify=False,
            )
            self.assertEqual(200, response.status_code)

    def test_170_admin_delete_template(self):
        response = requests.get(
            self.base + "/admin/jwt/local-default-admin-admin",
            headers=self.auths["isardvdi"]["header"],
            verify=False,
        )
        self.assertEqual(200, response.status_code)
        jwt = json.loads(response.text)["jwt"]

        response = requests.delete(
            self.base + "/template/_local-default-admin-admin-API_TEST_TEMPLATE",
            headers={"Authorization": "Bearer " + jwt},
            verify=False,
        )
        self.assertEqual(200, response.status_code)

    def test_180_admin_delete_group(self):
        response = requests.delete(
            self.base + "/admin/group/API_TESTS_CATEGORY_NAME-API_TESTS_GROUP_NAME",
            headers=self.auths["isardvdi"]["header"],
            verify=False,
        )
        self.assertEqual(200, response.status_code)

    def test_190_admin_delete_category(self):
        response = requests.delete(
            self.base + "/admin/category/API_TESTS_CATEGORY_NAME",
            headers=self.auths["isardvdi"]["header"],
            verify=False,
        )
        self.assertEqual(200, response.status_code)


if __name__ == "__main__":
    unittest.main()
