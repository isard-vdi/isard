#
#   Copyright © 2023 Miriam Melina Gamboa Valdez
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

import logging
import os
import traceback

from isardvdi_common.api_exceptions import Error
from isardvdi_common.api_rest import ApiRest
from rethinkdb import RethinkDB

from api import app

from .flask_rethink import RDB

notifier_client = ApiRest("isard-notifier")
logger = logging.getLogger(__name__)

r = RethinkDB()
db = RDB(app)
db.init_app(app)


def send_verification_email(email, user_id, token):
    try:
        data = {
            "email": email,
            "user_id": user_id,
            "url": "https://"
            + os.environ.get("DOMAIN")
            + "/verify-email?token={token}".format(token=token),
        }
        user = notifier_client.post("/mail/email-verify", data)
        return user
    except:
        raise Error(
            "internal_server",
            "Exception when sending verification email to user",
            traceback.format_exc(),
        )


def notify_backup_failure(backup_data):
    """Email active admins when a backup record is stored with a bad status.

    Best-effort: every failure inside is caught and logged. This must not
    interfere with the insert that triggered it — if the notifier is down,
    the backup record is still persisted.
    """
    status = backup_data.get("status")
    if status not in ("CRITICAL", "ERROR"):
        return

    scope = backup_data.get("scope", "full")
    summary = backup_data.get("summary", "")
    backup_type = backup_data.get("type", "automated")

    subject = f"[IsardVDI] Backup {status} ({scope})"
    text = (
        f"<p>An {backup_type} backup finished with status "
        f"<strong>{status}</strong>.</p>"
        f"<p>{summary or 'No summary available.'}</p>"
        f"<p>Review the full record in the admin panel under "
        f"<em>Backups</em>.</p>"
    )

    try:
        with app.app_context():
            admins = list(
                r.table("users")
                .get_all("admin", index="role")
                .filter(
                    lambda u: u["active"].default(False).eq(True)
                    & u["email"].default("").ne("")
                )
                .pluck("id", "username", "email")
                .run(db.conn)
            )
    except Exception as e:
        logger.warning("notify_backup_failure: cannot list admins: %s", e)
        return

    if not admins:
        logger.info(
            "notify_backup_failure: no active admins with an email address; "
            "skipping notification for %s",
            status,
        )
        return

    for admin in admins:
        try:
            notifier_client.post(
                "/mail",
                {
                    "user_id": admin["id"],
                    "subject": subject,
                    "text": text,
                },
            )
        except Exception as e:
            logger.warning(
                "notify_backup_failure: failed to notify admin %s: %s",
                admin.get("username") or admin.get("id"),
                e,
            )
