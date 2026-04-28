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

import os
import traceback
from typing import Any, Iterable

from isardvdi_common.helpers.error_factory import Error

_SERVICE = "isard-apiv4"


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
