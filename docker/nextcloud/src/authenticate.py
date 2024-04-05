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
import os
import shlex
import subprocess
import time

from _common.api_rest import ApiRest

api = ApiRest("isard-api")
api.wait_for()

# WARNING: We need to launch this script after nextcloud is up and running
time.sleep(5)
intra_docker = True if os.environ.get("NEXTCLOUD_INSTANCE", "") == "true" else False
domain = os.environ.get("DOMAIN", "")
# NOTE: If we use commercial certificate admin should toggle this to True in webapp
verify_cert = True if os.environ.get("LETSENCRYPT_EMAIL") else False
login_name = os.environ.get("NEXTCLOUD_ADMIN_USER", "isardvdi")
# Each nextcloud start a new secret will be updated in isardvdi
# Coming in v28. See https://github.com/nextcloud/server/pull/40026
# old_pws = json.loads(
#     subprocess.getoutput(
#         f'su -p "www-data" -s /bin/sh -c "/usr/local/bin/php occ user:auth-tokens --output=json_pretty {login_name}"'
#     )
# )
# for pw in old_pws:
#     subprocess.getoutput(
#         'su -p "www-data" -s /bin/sh -c "/usr/local/bin/php occ user:delete-auth-token '
#         + pw["id"]
#         + '"'
#     )
# Meanwhile we will be creating new one at each start
app_password = subprocess.run(
    shlex.split(
        f'su -p "www-data" -s /bin/sh -c "/usr/local/bin/php /var/www/html/occ user:add-app-password --password-from-env {login_name}"'
    ),
    capture_output=True,
    text=True,
).stdout.split("\n")[-1]
print(
    f"Registering/Updating nextcloud instance in {domain} IsardVDI with login {login_name} and new generated app password."
)
data = {
    "user": login_name,
    "password": app_password,
    "domain": domain,
    "verify_cert": verify_cert,
    "intra_docker": intra_docker,
}
resp = api.post(f"/admin/user_storage/auto_register", data=data)
print("Nextcloud registered with id: " + resp["id"])
