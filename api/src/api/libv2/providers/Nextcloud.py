#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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
import traceback
import xml.etree.ElementTree as ET

import gevent
import requests
from rethinkdb import RethinkDB

from ..._common.api_exceptions import Error, RequestObj
from ...libv2.log import *

r = RethinkDB()

from ..flask_rethink import RDB

db = RDB(app)
db.init_app(app)


def parse_dav_propstat(xml_data):
    root = ET.fromstring(xml_data)
    propstat_elem = root.find(".//{DAV:}propstat")

    prop_dict = {}
    for prop_elem in propstat_elem.findall("{DAV:}prop/*"):
        item = prop_elem.tag.replace("{DAV:}", "")
        value = prop_elem.text.strip() if prop_elem.text else ""
        prop_dict[item] = value
    return prop_dict


def _request(
    method,
    url,
    data={},
    headers={"OCS-APIRequest": "true"},
    auth=None,
    verify_cert=True,
):
    try:
        resp = requests.request(
            method,
            url,
            data=data,
            auth=auth,
            verify=verify_cert,
            headers=headers,
        )
    ## At least the ProviderSslError is not being catched or not raised correctly
    except requests.exceptions.HTTPError as errh:
        raise Error("gateway_timeout", "HTTP Error", traceback.format_exc())
    except requests.exceptions.Timeout as errt:
        raise Error("gateway_timeout", "HTTP Timeout", traceback.format_exc())
    except requests.exceptions.SSLError as err:
        raise Error("bad_request", "HTTP SSL Error", traceback.format_exc())
    except requests.exceptions.ConnectionError as errc:
        raise Error(
            "gateway_timeout",
            "HTTP Provider connection error",
            traceback.format_exc(),
        )
    except requests.exceptions.RequestException:
        raise Error(
            "internal_server",
            "HTTP Provider connection error",
            traceback.format_exc(),
        )
    if resp.status_code == 401:
        raise Error(
            "bad_request",
            "HTTP Provider unauthorized. Check your credentials or bruteforce block by provider.",
        )
    if resp.status_code == 404:
        raise Error(
            "not_found",
            "HTTP Provider url " + url + " not found.",
        )
    if resp.status_code == 499:
        raise Error(
            "not_found",
            "HTTP Provider unexpected closed connection.",
        )
    if method == "MKCOL":
        # This method returns 201 if created, 405 if already exists and other codes
        # Should do tests
        if resp.status_code == 405:
            raise Error(
                "conflict",
                "Folder already exists",
                traceback.format_exc(),
            )
        if resp.status_code != 201:
            raise Error(
                "internal_server",
                "HTTP Provider MKCOL connection error with status code: "
                + str(resp.status_code),
                traceback.format_exc(),
            )
        return resp.text
    if method == "PROPFIND":
        # This method returns 207 if exists, 405 if already exists and other codes
        # Should do tests
        if resp.status_code == 405:
            raise Error(
                "conflict",
                "Folder already exists",
                traceback.format_exc(),
            )
        if resp.status_code != 207:
            raise Error(
                "internal_server",
                "HTTP Provider PROPFIND connection error with status code: "
                + str(resp.status_code),
                traceback.format_exc(),
            )
        return resp.text
    if resp.status_code not in [302, 304, 200]:
        raise Error(
            "internal_server",
            "HTTP Provider connection error with status code: " + str(resp.status_code),
            traceback.format_exc(),
        )
    return resp.text


### Login auth v2
login_thread = None


def start_login_auth(provider_id):
    global login_thread
    if login_thread:
        login_thread.kill()
    with app.app_context():
        provider = r.table("user_storage").get(provider_id).run(db.conn)
    login_url = "https://" + provider["url"] + provider["urlprefix"]
    headers = {
        "ACCEPT_LANGUAGE": "en-US,en;q=0.5",
        "USER_AGENT": "Mozilla/5.0 (X11; Linux x86_64; rv:68.0) Gecko/20100101 Firefox/68.0",
    }
    data = json.loads(
        _request(
            "POST",
            login_url + "/index.php/login/v2",
            headers=headers,
            verify_cert=provider["verify_cert"],
        )
    )
    if data.get("poll", {}).get("token"):
        # Launch thread to see if user has logged in and wait for it
        # Nextcloud allows for 20 minutes, we are not that patient
        # We will wait 5 minutes. Thread will be started in 5 seconds...
        # https://docs.nextcloud.com/server/latest/developer_manual/client_apis/LoginFlow/index.html#login-flow-v2
        login_thread = gevent.spawn_later(
            5, get_login_auth_callback, data["poll"]["token"], login_url, provider_id
        )
        # gevent.joinall([login_thread], timeout=5 * 60, raise_error=False)
    # Should be opened in a new window
    return data.get("login")


def get_login_auth_callback(token, login_url, provider_id):
    # If we got the credentials, we can finish the thread after
    # updating login credentials into database
    # How will notify the user that registration was completed?
    # socket.emit to the client and form close and table reload with connection status
    while True:
        time.sleep(1)
        result = json.loads(
            _request(
                "POST",
                login_url + "/login/v2/poll",
                data={"token": token},
                headers={"OCS-APIRequest": "true"},
            )
        )
        if "loginName" in result and "appPassword" in result:
            with app.app_context():
                r.table("user_storage").get(provider_id).update(
                    {
                        "user": result["loginName"],
                        "password": result["appPassword"],
                    }
                ).run(db.conn)
            break


class NextcloudApi:
    def __init__(self, domain, verify_cert, intra_docker=False):
        self.verify_cert = verify_cert
        self.auth_protocol = None
        self.auth = None
        self.webdav_auth = None
        self.token = None
        protocol = "http://" if intra_docker else "https://"
        domain = "isard-nc-nginx/isard-nc" if intra_docker else domain
        self.apiurl = protocol + domain + "/ocs/v1.php/cloud/"
        self.shareurl = protocol + domain + "/ocs/v2.php/apps/files_sharing/api/v1/"
        self.davurl = protocol + domain + "/remote.php/dav/files/"

    def set_basic_auth(self, user, password):
        self.auth = (user, password)
        self.user = user
        self.auth_protocol = "basic"

    def set_webdav_auth(self, user, password):
        self.webdav_auth = (user, password)

    def _request(
        self,
        method,
        url,
        data={},
        headers={"OCS-APIRequest": "true"},
        auth=None,
        timeout=None,
    ):
        app.logger.debug(
            "NextcloudApi request: "
            + str(method)
            + " "
            + str(url)
            + " "
            + str(data)
            + " "
            + str(headers)
            + " "
            + str(auth)
        )
        if not self.auth_protocol:
            raise Error("bad_request", "No auth protocol set")
        if not auth:
            auth = self.auth
        if self.auth_protocol == "basic":
            try:
                resp = requests.request(
                    method,
                    url,
                    data=data,
                    auth=auth,
                    verify=self.verify_cert,
                    headers=headers,
                    timeout=timeout,
                )
            ## At least the ProviderSslError is not being catched or not raised correctly
            except requests.exceptions.HTTPError as errh:
                raise Error("gateway_timeout", "HTTP Error", traceback.format_exc())
            except requests.exceptions.Timeout as errt:
                raise Error("gateway_timeout", "HTTP Timeout", traceback.format_exc())
            except requests.exceptions.SSLError as err:
                raise Error("bad_request", "HTTP SSL Error", traceback.format_exc())
            except requests.exceptions.ConnectionError as errc:
                raise Error(
                    "gateway_timeout",
                    "HTTP Provider connection error",
                    traceback.format_exc(),
                )
            except requests.exceptions.RequestException:
                raise Error(
                    "internal_server",
                    "HTTP Provider connection error",
                    traceback.format_exc(),
                )
            if resp.status_code == 401:
                raise Error(
                    "bad_request",
                    "HTTP Provider unauthorized. Check your credentials or bruteforce block by provider.",
                )
            if resp.status_code == 404:
                raise Error(
                    "not_found",
                    "HTTP Provider url " + url + " not found.",
                )
            if resp.status_code == 499:
                raise Error(
                    "not_found",
                    "HTTP Provider unexpected closed connection.",
                )
            if method == "MKCOL":
                # This method returns 201 if created, 405 if already exists and other codes
                # Should do tests
                if resp.status_code == 405:
                    raise Error(
                        "conflict",
                        "Folder already exists",
                        traceback.format_exc(),
                    )
                if resp.status_code != 201:
                    raise Error(
                        "internal_server",
                        "HTTP Provider MKCOL connection error with status code: "
                        + str(resp.status_code),
                        traceback.format_exc(),
                    )
                return resp.text
            if method == "PROPFIND":
                # This method returns 207 if exists, 405 if already exists and other codes
                # Should do tests
                if resp.status_code == 405:
                    raise Error(
                        "conflict",
                        "Folder already exists",
                        traceback.format_exc(),
                    )
                if resp.status_code != 207:
                    raise Error(
                        "internal_server",
                        "HTTP Provider PROPFIND connection error with status code: "
                        + str(resp.status_code),
                        traceback.format_exc(),
                    )
                return resp.text
            if resp.status_code not in [302, 304, 200]:
                raise Error(
                    "internal_server",
                    "HTTP Provider connection error with status code: "
                    + str(resp.status_code),
                    traceback.format_exc(),
                )
            return resp.text

    def check_connection(self, timeout=2):
        url = self.apiurl + "users/" + self.user + "?format=json"
        self._request("GET", url)
        return True

    def get_user(self, user_id):
        if user_id == "admin":
            raise Error("bad_request", "user_id cannot be admin")
        url = self.apiurl + "users/" + user_id + "?format=json"
        result = json.loads(self._request("GET", url))
        if result["ocs"]["meta"]["statuscode"] == 100:
            return result["ocs"]["data"]
        raise Error(
            "not_found",
            "Provider user " + user_id + " not found",
            custom_request=RequestObj("GET", url, headers={"OCS-APIRequest": "true"}),
        )

    def get_users(self):
        url = self.apiurl + "users?format=json"
        # try:
        result = json.loads(self._request("GET", url))
        if result["ocs"]["meta"]["statuscode"] == 100:
            try:
                result["ocs"]["data"]["users"].remove("admin")
            except ValueError:
                pass
            return result["ocs"]["data"]["users"]
        raise Error(
            "not_found",
            "Get provider users list error: " + str(result),
            traceback.format_exc(),
            custom_request=RequestObj("GET", url, headers={"OCS-APIRequest": "true"}),
        )

    def get_user_quota(self, user_id):
        if user_id == "admin":
            raise Error("bad_request", "user_id cannot be admin")
        url = self.apiurl + "users/" + user_id + "?format=json"
        result = json.loads(self._request("GET", url))
        if result["ocs"]["meta"]["statuscode"] == 100:
            if "free" not in result["ocs"]["data"]["quota"]:
                return {
                    "free": 0.0,
                    "quota": result["ocs"]["data"]["quota"]["quota"] / 1024 / 1024,
                    "relative": 0.0,
                    "total": 0.0,
                    "used": result["ocs"]["data"]["quota"]["used"] / 1024 / 1024,
                }
            return {
                "free": result["ocs"]["data"]["quota"]["free"] / 1024 / 1024,
                "quota": result["ocs"]["data"]["quota"]["quota"] / 1024 / 1024,
                "relative": result["ocs"]["data"]["quota"]["relative"],
                "total": result["ocs"]["data"]["quota"]["total"] / 1024 / 1024,
                "used": result["ocs"]["data"]["quota"]["used"] / 1024 / 1024,
            }
        raise Error(
            "not_found",
            "Provider user "
            + str(user_id)
            + " not found. Provider reported error: "
            + str(
                result.get("ocs", {})
                .get("meta", {})
                .get("message", "NO ERROR MESSAGE PROVIDED")
            ),
            custom_request=RequestObj("GET", url, headers={"OCS-APIRequest": "true"}),
        )

    def add_user(
        self, user_id, password, quota_MB, groups=[], email="", displayname=""
    ):
        data = {
            "userid": user_id,
            "password": password,
            "quota": str(quota_MB) + "MB",
            "groups[]": groups,
            "email": email,
            "displayName": displayname,
        }
        url = self.apiurl + "users?format=json"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        result = json.loads(self._request("POST", url, data=data, headers=headers))
        if result["ocs"]["meta"]["statuscode"] == 100:
            return True
        if result["ocs"]["meta"]["statuscode"] == 101:
            raise Error(
                "bad_request",
                "User " + user_id + " with bad data: ",
                +result.get("ocs")
                .get("meta")
                .get("message", "NO ERROR MESSAGE PROVIDED"),
                custom_request=RequestObj(
                    "POST",
                    url,
                    data=data,
                    headers={"OCS-APIRequest": "true"},
                ),
            )
        if result["ocs"]["meta"]["statuscode"] == 102:
            raise Error(
                "conflict",
                "User "
                + user_id
                + " already exists: "
                + result.get("ocs")
                .get("meta")
                .get("message", "NO ERROR MESSAGE PROVIDED"),
                custom_request=RequestObj(
                    "POST", url, data=data, headers={"OCS-APIRequest": "true"}
                ),
            )
        if result["ocs"]["meta"]["statuscode"] == 104:
            raise Error(
                "not_found",
                "Provider user group not found: "
                + result.get("ocs")
                .get("meta")
                .get("message", "NO ERROR MESSAGE PROVIDED"),
                custom_request=RequestObj(
                    "POST", url, data=data, headers={"OCS-APIRequest": "true"}
                ),
            )
        if result["ocs"]["meta"]["statuscode"] == 107:
            raise Error(
                "bad_request",
                "User password too weak: "
                + result.get("ocs")
                .get("meta")
                .get("message", "NO ERROR MESSAGE PROVIDED"),
                custom_request=RequestObj(
                    "POST", url, data=data, headers={"OCS-APIRequest": "true"}
                ),
            )
        raise Error(
            "internal_server",
            "Nextcloud provider user add error: " + str(result),
            traceback.format_exc(),
            custom_request=RequestObj(
                "POST", url, data=data, headers={"OCS-APIRequest": "true"}
            ),
        )

    def remove_user(self, user_id):
        if user_id == "admin":
            app.logger.debug("Nextcloud admin user cannot be removed")
            return
        url = self.apiurl + "users/" + user_id + "?format=json"
        result = json.loads(self._request("DELETE", url))
        if result["ocs"]["meta"]["statuscode"] == 100:
            return True
        if result["ocs"]["meta"]["statuscode"] == 101:
            raise Error(
                "not_found",
                "Unable to remove inexisting user"
                + user_id
                + ": "
                + result.get("ocs")
                .get("meta")
                .get("message", "NO ERROR MESSAGE PROVIDED"),
                custom_request=RequestObj(
                    "DELETE", url, headers={"OCS-APIRequest": "true"}
                ),
            )
        raise Error(
            "internal_server",
            "HTTP Provider remove user internal error: ",
            traceback.format_exc(),
            custom_request=RequestObj(
                "DELETE", url, headers={"OCS-APIRequest": "true"}
            ),
        )

    def update_user(
        self, user_id, password=None, quota_MB=None, email=None, displayname=None
    ):
        data_input = {}
        if email:
            data_input["email"] = email
        if displayname:
            data_input["displayname"] = displayname
        if password:
            data_input["password"] = password
        if quota_MB:
            data_input["quota"] = str(quota_MB) + "MB"

        # {'enabled': True,
        #  'storageLocation': '/var/www/html/data/5a660c5c-ab40-4dd8-9234-764d7d766a6c',
        #  'id': '5a660c5c-ab40-4dd8-9234-764d7d766a6c',
        #  'lastLogin': 1687870788000,
        #  'backend': 'Database',
        #  'subadmin': ['08e1622a-dadd-4935-a073-7179541e5aba', '67a9ae07-a1bb-4846-8ed9-ee43295059b3'],
        #  'quota': {'free': 104857600, 'used': 0, 'total': 104857600, 'relative': 0, 'quota': 104857600},
        #  'manager': '',
        #  'email': 'mail@mail.com',
        #  'additional_mail': [],
        #  'displayname': 'Hander Nou 1',
        #  'display-name': 'Hander Nou 1',
        #  'phone': '',
        #  'address': '',
        #  'website': '',
        #  'twitter': '',
        #  'fediverse': '',
        #  'organisation': '',
        #  'role': '',
        #  'headline': '',
        #  'biography': '',
        #  'profile_enabled': '0',
        #  'groups': ['67a9ae07-a1bb-4846-8ed9-ee43295059b3', '08e1622a-dadd-4935-a073-7179541e5aba'],
        #  'language': 'ca',
        #  'locale': '',
        #  'notify_email': None,
        #  'backendCapabilities': {'setDisplayName': True, 'setPassword': True}}"

        for k, v in data_input.items():
            data = {"key": k, "value": v}

            url = self.apiurl + "users/" + user_id + "?format=json"
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "OCS-APIRequest": "true",
            }
            result = json.loads(self._request("PUT", url, data=data, headers=headers))
            if result["ocs"]["meta"]["statuscode"] == 100:
                continue
            if result["ocs"]["meta"]["statuscode"] == 101:
                raise Error(
                    "not_found",
                    "User "
                    + user_id
                    + " not found to be updated. Provider reported error: "
                    + str(
                        result.get("ocs", {})
                        .get("meta", {})
                        .get("message", "NO ERROR MESSAGE PROVIDED")
                    ),
                    custom_request=RequestObj("PUT", url, data=data, headers=headers),
                )
            if result["ocs"]["meta"]["statuscode"] == 102:
                raise Error(
                    "bad_request",
                    "User "
                    + user_id
                    + " bad parameters to be updated. Provider reported error: "
                    + str(
                        result.get("ocs", {})
                        .get("meta", {})
                        .get("message", "NO ERROR MESSAGE PROVIDED")
                    ),
                    custom_request=RequestObj("PUT", url, data=data, headers=headers),
                )
            raise Error(
                "internal_server",
                "Provider update user "
                + user_id
                + ". Provider reported error: "
                + str(result),
                custom_request=RequestObj("PUT", url, data=data, headers=headers),
            )
        return True

    def add_subadmin(self, user_id, group_id):
        data = {
            "groupid": group_id,
        }
        url = self.apiurl + "users/" + user_id + "/subadmins?format=json"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        result = json.loads(self._request("POST", url, data=data, headers=headers))
        if result["ocs"]["meta"]["statuscode"] == 100:
            return True
        if result["ocs"]["meta"]["statuscode"] == 101:
            raise Error(
                "not_found",
                "User "
                + user_id
                + " not found, so can't be scalated to subadmin: "
                + result.get("ocs").get("meta").get("message"),
                custom_request=RequestObj("POST", url, data=data, headers=headers),
            )
        if result["ocs"]["meta"]["statuscode"] == 102:
            raise Error(
                "not_found",
                "Group "
                + group_id
                + " not found, so user "
                + user_id
                + " can't be added as subadmin: "
                + result.get("ocs").get("meta").get("message"),
                custom_request=RequestObj("POST", url, data=data, headers=headers),
            )
        raise Error(
            "internal_server",
            "Nextcloud provider user "
            + user_id
            + " scalate to subadmin error: "
            + str(result),
            traceback.format_exc(),
            custom_request=RequestObj("POST", url, data=data, headers=headers),
        )

    def delete_subadmin(self, user_id, group_id):
        data = {
            "groupid": group_id,
        }
        url = self.apiurl + "users/" + user_id + "/subadmins?format=json"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        result = json.loads(self._request("DELETE", url, data=data, headers=headers))
        if result["ocs"]["meta"]["statuscode"] == 100:
            return True
        if result["ocs"]["meta"]["statuscode"] == 101:
            raise Error(
                "not_found",
                "User "
                + user_id
                + " not found, so can't be de-scalated from subadmin: "
                + result.get("ocs").get("meta").get("message"),
                custom_request=RequestObj("DELETE", url, data=data, headers=headers),
            )
        if result["ocs"]["meta"]["statuscode"] == 102:
            raise Error(
                "not_found",
                "Group "
                + group_id
                + " not found or user is not subadmin, so user "
                + user_id
                + " can't be removed as subadmin of this group: "
                + result.get("ocs").get("meta").get("message"),
                custom_request=RequestObj("DELETE", url, data=data, headers=headers),
            )
        raise Error(
            "internal_server",
            "Nextcloud provider user "
            + user_id
            + " de scalate from subadmin error: "
            + str(result),
            traceback.format_exc(),
            custom_request=RequestObj("DELETE", url, data=data, headers=headers),
        )

    def enable_user(self, user_id):
        if user_id == "admin":
            app.logger.debug("Nextcloud admin user cannot be enabled")
            return
        url = self.apiurl + "users/" + user_id + "/enable?format=json"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        result = json.loads(self._request("PUT", url, headers=headers))
        if result["ocs"]["meta"]["statuscode"] == 100:
            return True
        if result["ocs"]["meta"]["statuscode"] == 101:
            raise Error(
                "not_found",
                "Unable to enable unexisting user "
                + user_id
                + ": "
                + result.get("ocs")
                .get("meta")
                .get("message", "NO ERROR MESSAGE PROVIDED"),
                custom_request=RequestObj("PUT", url, headers=headers),
            )

        raise Error(
            "internal_server",
            "HTTP Provider disable user internal error: " + str(result),
            traceback.format_exc(),
            custom_request=RequestObj("PUT", url, headers=headers),
        )

    def disable_user(self, user_id):
        if user_id == "admin":
            app.logger.debug("Nextcloud admin user cannot be disabled")
            return
        url = self.apiurl + "users/" + user_id + "/disable?format=json"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        result = json.loads(self._request("PUT", url, headers=headers))
        if result["ocs"]["meta"]["statuscode"] == 100:
            return True
        if result["ocs"]["meta"]["statuscode"] == 101:
            raise Error(
                "not_found",
                "Unable to disable unexisting user "
                + user_id
                + ": "
                + result.get("ocs")
                .get("meta")
                .get("message", "NO ERROR MESSAGE PROVIDED"),
                custom_request=RequestObj("PUT", url, headers=headers),
            )

        raise Error(
            "internal_server",
            "HTTP Provider disable user internal error: " + str(result),
            traceback.format_exc(),
            custom_request=RequestObj("PUT", url, headers=headers),
        )

    def exists_user_folder(self, user_id, password, folder="IsardVDI"):
        auth = (user_id, password)
        url = self.davurl + user_id + "/" + folder
        headers = {
            "Depth": "0",
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        try:
            self._request("PROPFIND", url, auth=auth, headers=headers)
            return True
            # {
            #     'getlastmodified': 'Tue, 06 Jun 2023 16:29:47 GMT',
            #     'resourcetype': '',
            #     'quota-used-bytes': '5656463',
            #     'quota-available-bytes': '2120946499',
            #     'getetag': '"647f5efb98683"'
            # }
        except Error as e:
            if e.status_code == 404:
                return False
        except:
            raise Error(
                "internal_server",
                "Nextcloud exists_user_folder error: ",
                traceback.format_exc(),
                custom_request=RequestObj("PROPFIND", url, auth=auth, headers=headers),
            )

    def add_user_folder(
        self, user_id, password, folder="IsardVDI", skip_if_exists=True
    ):
        auth = (user_id, password)
        url = self.davurl + user_id + "/" + folder
        headers = {
            "Depth": "0",
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        try:
            self._request("MKCOL", url, auth=auth, headers=headers)
            return True
        except Error as e:
            if e.status_code == 409:
                if skip_if_exists:
                    return True
                raise Error(
                    "conflict",
                    "User " + user_id + " folder " + folder + " already exists",
                    custom_request=RequestObj("MKCOL", url, auth=auth, headers=headers),
                )

    def get_user_share_folder_data(self, user_id, password, folder="IsardVDI"):
        return self.exists_user_share_folder(user_id, password, folder)

    def exists_user_share_folder(self, user_id, password, folder="IsardVDI"):
        auth = (user_id, password)
        url = self.shareurl + "shares?format=json"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        result = json.loads(self._request("GET", url, auth=auth, headers=headers))
        share = [s for s in result["ocs"]["data"] if s["path"] == "/" + folder]
        if len(share) >= 1:
            return {"token": share[0]["token"], "url": share[0]["url"]}
        return False

    def add_user_share_folder(
        self,
        user_id,
        password,
        permissions=31,
        folder="IsardVDI",
        reset_if_exists=False,
    ):
        # POST Arguments: https://docs.nextcloud.com/server/20/developer_manual/client_apis/OCS/ocs-share-api.html#create-a-new-share
        if not reset_if_exists and self.exists_user_share_folder(
            user_id, password, folder
        ):
            raise Error(
                "conflict",
                "User "
                + user_id
                + " shared folder "
                + folder
                + " already exists, so it cannot be shared again",
            )
        auth = (user_id, password)
        data = {"path": "/" + folder, "shareType": 3, "permissions": permissions}
        url = self.shareurl + "shares?format=json"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        try:
            result = json.loads(
                self._request("POST", url, data=data, auth=auth, headers=headers)
            )
            return {
                "token": result["ocs"]["data"]["token"],
                "url": result["ocs"]["data"]["url"],
            }
        except Error as e:
            if e.status_code == 404:
                raise Error(
                    "not_found",
                    "User "
                    + user_id
                    + " folder "
                    + folder
                    + " does not exist, so it cannot be shared",
                    custom_request=RequestObj(
                        "POST", url, data=data, auth=auth, headers=headers
                    ),
                )
        except:
            raise Error(
                "internal_server",
                "Nextcloud exists_user_shared_folder error: ",
                traceback.format_exc(),
                custom_request=RequestObj(
                    "POST", url, data=data, auth=auth, headers=headers
                ),
            )

    def exists_group(self, group_id):
        url = self.apiurl + "groups?search=" + group_id + "&format=json"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        result = json.loads(self._request("GET", url, auth=self.auth, headers=headers))
        return True if group_id in result["ocs"]["data"]["groups"] else False

    def get_groups(self):
        url = self.apiurl + "groups?format=json"
        result = json.loads(self._request("GET", url))
        try:
            result["ocs"]["data"]["groups"].remove("admin")
        except ValueError:
            pass
        return result["ocs"]["data"]["groups"]

    def get_group_members(self, group_id):
        url = self.apiurl + f"groups/{group_id}?format=json"
        result = json.loads(self._request("GET", url))
        if not len(result["ocs"]["data"]):
            return []
        try:
            result["ocs"]["data"]["users"].remove("admin")
        except ValueError:
            pass
        return result["ocs"]["data"]["users"]

    def add_group(self, group_id, skip_if_exists=True):
        data = {"groupid": group_id}
        url = self.apiurl + "groups?format=json"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        result = json.loads(
            self._request("POST", url, data=data, auth=self.auth, headers=headers)
        )
        if result["ocs"]["meta"]["statuscode"] == 100:
            return True
        if result["ocs"]["meta"]["statuscode"] == 102:
            if not skip_if_exists:
                raise Error(
                    "conflict",
                    "Group " + group_id + " already exists",
                    custom_request=RequestObj(
                        "POST", url, data=data, auth=self.auth, headers=headers
                    ),
                )
            app.logger.error("Group " + group_id + " already exists")
            return True
        raise Error(
            "internal_server",
            "HTTP Provider add group internal error",
            traceback.format_exc(),
            custom_request=RequestObj(
                "POST", url, data=data, auth=self.auth, headers=headers
            ),
        )

    def remove_group(self, group_id, skip_if_not_exists=True):
        url = self.apiurl + "groups/" + group_id + "?format=json"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        result = json.loads(
            self._request("DELETE", url, auth=self.auth, headers=headers)
        )
        if result["ocs"]["meta"]["statuscode"] == 100:
            return True
        if not skip_if_not_exists and result["ocs"]["meta"]["statuscode"] == 101:
            raise Error(
                "not_found",
                "Group " + group_id + " does not exist, so it cannot be removed",
                custom_request=RequestObj(
                    "DELETE", url, auth=self.auth, headers=headers
                ),
            )
        return True

    def update_group(self, group_id, new_group_name):
        data = {"key": "displayname", "value": new_group_name}

        url = self.apiurl + "groups/" + group_id + "?format=json"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "OCS-APIRequest": "true",
        }
        result = json.loads(self._request("PUT", url, data=data, headers=headers))
        if result["ocs"]["meta"]["statuscode"] == 100:
            return True
        if result["ocs"]["meta"]["statuscode"] == 101:
            raise Error(
                "not_found",
                "Group "
                + group_id
                + " not found to be updated. Provider reported error: "
                + str(
                    result.get("ocs", {})
                    .get("meta", {})
                    .get("message", "NO ERROR MESSAGE PROVIDED")
                ),
                custom_request=RequestObj("PUT", url, data=data, headers=headers),
            )
        if result["ocs"]["meta"]["statuscode"] == 102:
            raise Error(
                "bad_request",
                "Group "
                + group_id
                + " bad parameters to be updated. Provider reported error: "
                + str(
                    result.get("ocs", {})
                    .get("meta", {})
                    .get("message", "NO ERROR MESSAGE PROVIDED")
                ),
                custom_request=RequestObj("PUT", url, data=data, headers=headers),
            )
        raise Error(
            "internal_server",
            "Provider update group "
            + group_id
            + ". Provider reported error: "
            + str(result),
            custom_request=RequestObj("PUT", url, data=data, headers=headers),
        )
