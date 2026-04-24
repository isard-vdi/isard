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

"""Python façade over the generated isard-notifier client.

All imports of the generated client and its helpers are kept lazy so
services that ship ``isardvdi_common`` but never actually call a
notifier endpoint don't need the ``isardvdi_notifier_client`` package
installed.
"""

import logging
import os
import traceback
from typing import Any, Iterable

from isardvdi_common.helpers.error_factory import Error

_SERVICE = "isard-apiv4"

logger = logging.getLogger(__name__)


def send_verification_email(email: str, user_id: str, token: str) -> Any:
    """Trigger a verification email via isard-notifier.

    Returns the parsed response body (typically contains the task id).
    """
    from isardvdi_notifier_client.api.mail import post_notifier_mail_email_verify
    from isardvdi_notifier_client.models import NotifyEmailVerifyMailRequest
    from isardvdi_notifier_client_auth import build_client, raise_for_status

    try:
        with build_client(_SERVICE) as client:
            resp = post_notifier_mail_email_verify.sync_detailed(
                client=client,
                body=NotifyEmailVerifyMailRequest(
                    email=email,
                    user_id=user_id,
                    url="https://{domain}/verify-email?token={token}".format(
                        domain=os.environ.get("DOMAIN"),
                        token=token,
                    ),
                ),
            )
            raise_for_status(resp)
            return resp.parsed
    except Error:
        raise
    except Exception:
        raise Error(
            "internal_server",
            "Exception when sending verification email to user",
            traceback.format_exc(),
        )


def notify_backup_failure(backup_data: dict) -> None:
    """Email active admins when a backup record is stored with a bad status.

    Best-effort: every failure inside is caught and logged. This must not
    interfere with the insert that triggered it — if the notifier is down,
    the backup record is still persisted.
    """
    status = backup_data.get("status")
    if status not in ("CRITICAL", "ERROR"):
        return

    # Lazy imports keep services that don't ship the notifier client able to
    # import this module without ``ModuleNotFoundError``.
    from isardvdi_notifier_client.api.mail import post_notifier_mail
    from isardvdi_notifier_client.models import NotifyMailRequest
    from isardvdi_notifier_client_auth import build_client, raise_for_status
    from rethinkdb import r

    from isardvdi_common.connections.rethink_connection_factory import (
        RethinkSharedConnection,
    )

    host = backup_data.get("host", "unknown")
    scope = backup_data.get("scope", "full")
    summary = backup_data.get("summary", "")
    backup_type = backup_data.get("type", "automated")

    subject = f"[IsardVDI] Backup {status} on {host} ({scope})"
    text = (
        f"<p>An {backup_type} backup on host <strong>{host}</strong> "
        f"finished with status <strong>{status}</strong>.</p>"
        f"<p>{summary or 'No summary available.'}</p>"
        f"<p>Review the full record in the admin panel under "
        f"<em>Backups</em>.</p>"
    )

    try:
        with RethinkSharedConnection._rdb_context():
            admins = list(
                r.table("users")
                .get_all("admin", index="role")
                .filter(
                    lambda u: u["active"].default(False).eq(True)
                    & u["email"].default("").ne("")
                )
                .pluck("id", "username", "email")
                .run(RethinkSharedConnection._rdb_connection)
            )
    except Exception as e:
        logger.warning("notify_backup_failure: cannot list admins: %s", e)
        return

    if not admins:
        logger.info(
            "notify_backup_failure: no active admins with an email address; "
            "skipping notification for %s on %s",
            status,
            host,
        )
        return

    for admin in admins:
        try:
            with build_client(_SERVICE) as client:
                resp = post_notifier_mail.sync_detailed(
                    client=client,
                    body=NotifyMailRequest(
                        user_id=admin["id"],
                        subject=subject,
                        text=text,
                    ),
                )
                raise_for_status(resp)
        except Exception as e:
            logger.warning(
                "notify_backup_failure: failed to notify admin %s: %s",
                admin.get("username") or admin.get("id"),
                e,
            )


def send_deleted_gpu_notification(
    user_id: str,
    *,
    text: str = "",
    bookings: Iterable[dict] = (),
    desktops: Iterable[dict] = (),
    deployments: Iterable[dict] = (),
) -> Any:
    """Trigger a "GPU affected" email via isard-notifier.

    Returns the parsed response body.
    """
    from isardvdi_notifier_client.api.gpu import post_notifier_mail_deleted_gpu
    from isardvdi_notifier_client.models import NotifyDeleteGPUMailRequest
    from isardvdi_notifier_client_auth import build_client, raise_for_status

    with build_client(_SERVICE) as client:
        resp = post_notifier_mail_deleted_gpu.sync_detailed(
            client=client,
            body=NotifyDeleteGPUMailRequest(
                text=text,
                user_id=user_id,
                bookings=list(bookings),
                desktops=list(desktops),
                deployments=list(deployments),
            ),
        )
        raise_for_status(resp)
        return resp.parsed
