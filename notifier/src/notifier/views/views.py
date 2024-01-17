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
import os

from flask import render_template
from html_sanitizer import Sanitizer
from isardvdi_common.api_exceptions import Error
from isardvdi_common.task import Task
from jinja2.exceptions import TemplateNotFound
from spectree import Response

from notifier import api, app

from ..lib.api_actions import get_notification_message, get_user
from ..schemas import notifier
from .decorators import is_admin

sanitizer = Sanitizer(
    {
        "attributes": {"a": ("href", "name", "target", "title", "id", "rel", "class")},
    }
)


@app.route("/notifier/mail", methods=["POST"])
@api.validate(resp=Response(HTTP_200=notifier.NotifyMailResponse))
@is_admin
def notify_mail(payload, json: notifier.NotifyMailRequest):
    """
    Send an email to the user with the email specifications as JSON in body request.

    Email specifications in JSON:
    {
        "user_id": "User ID to be used to retrieve its email address",
        "subject": "subject of the email that will be sent",
        "text": "text of the email that will be sent",
    }
    :param payload: Data from JWT
    :type payload: dict
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    if not os.environ.get("NOTIFY_EMAIL"):
        return
    user = get_user(json.user_id)
    if not user.get("email"):
        raise Error("bad_request", "The given user does not have an email address.")
    email_html = render_template(
        "email/base.html",
        email_content=sanitizer.sanitize(json.text),
        email_footer="Si us plau no respongueu a aquest correu ja que ha estat generat automàticament.",
    )
    task_id = Task(
        queue="notifier.default",
        task="mail",
        user_id=json.user_id,
        job_kwargs={
            "kwargs": {
                "address": [user.get("email")],
                "subject": json.subject,
                "text": json.text,
                "html": email_html,
            },
        },
    ).id

    return notifier.NotifyMailResponse(task_id=task_id)


@app.route("/notifier/mail/email-verify", methods=["POST"])
@api.validate(resp=Response(HTTP_200=notifier.NotifyEmailVerifyMailResponse))
@is_admin
def email_verify(payload, json: notifier.NotifyEmailVerifyMailRequest):
    """
    Send an email to the user with the email specifications as JSON in body request.

    Email specifications in JSON:
    {
        "email": "email address where the mail will be sent",
        "url": "url that will be sent to the user for email verification",
    }
    :param payload: Data from JWT
    :type payload: dict
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    if not os.environ.get("NOTIFY_EMAIL"):
        return
    text = """Please go to the following address to verify you email address:\n
                {link}\n""".format(
        link=json.url
    )
    # TODO: get user_id and maybe change to a generic endpoint?
    email_content = get_notification_message(
        {"user_id": None, "event": "email-verify", "data": {"url": json.url}}
    )
    email_html = render_template(
        "email/base.html",
        email_content=sanitizer.sanitize(email_content["body"]),
        email_footer=email_content["footer"],
    )
    task_id = Task(
        queue="notifier.default",
        task="mail",
        job_kwargs={
            "kwargs": {
                "address": [json.email],
                "subject": email_content["title"],
                "text": text,
                "html": email_html,
            },
        },
    ).id

    return notifier.NotifyEmailVerifyMailResponse(task_id=task_id)


@app.route("/notifier/mail/password-reset", methods=["POST"])
@api.validate(resp=Response(HTTP_200=notifier.NotifyPasswordResetMailResponse))
@is_admin
def password_reset(payload, json: notifier.NotifyPasswordResetMailRequest):
    """
    Send an email to the user with the email specifications as JSON in body request.

    Email specifications in JSON:
    {
        "email": "email address where the mail will be sent",
        "url": "url that will be sent to the user for password reset",
    }
    :param payload: Data from JWT
    :type payload: dict
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    if not os.environ.get("NOTIFY_EMAIL"):
        return
    text = """We've received your password reset request to access IsardVDI. Go to the following address to set a new password:\n
                {link}\n""".format(
        link=json.url
    )
    # TODO: get user_id and maybe change to a generic endpoint?
    email_content = get_notification_message(
        {"user_id": None, "event": "password-reset", "data": {"url": json.url}}
    )
    email_html = render_template(
        "email/base.html",
        email_content=sanitizer.sanitize(email_content["body"]),
        email_footer=email_content["footer"],
    )
    task_id = Task(
        queue="notifier.default",
        task="mail",
        job_kwargs={
            "kwargs": {
                "address": [json.email],
                "subject": email_content["title"],
                "text": text,
                "html": email_html,
            },
        },
    ).id

    return notifier.NotifyPasswordResetMailResponse(task_id=task_id)


@app.route("/frontend", methods=["POST"])
@api.validate(resp=Response(HTTP_200=notifier.NotifyFrontendResponse))
def notify_frontend(json: notifier.NotifyFrontendRequest):
    """
    NotifyFrontend sends a popup notification to the user webpage interface
    """
    return notifier.NotifyFrontendResponse()


@app.route("/frontend/desktop-time-limit", methods=["POST"])
@api.validate(resp=Response(HTTP_200=notifier.NotifyFrontendDesktopTimeLimitResponse))
def notify_frontend_desktop_time_limit(
    json: notifier.NotifyFrontendDesktopTimeLimitRequest,
):
    """
    NotifyFrontendDesktopTimeLimit notifies the user that the time limit is approaching
    """
    return notifier.NotifyFrontendDesktopTimeLimitResponse()


@app.route("/frontend/searching-resources", methods=["POST"])
@api.validate(resp=Response(HTTP_200=notifier.NotifyFrontendSearchingResourcesResponse))
def notify_frontend_searching_resources(
    json: notifier.NotifyFrontendSearchingResourcesRequest,
):
    """
    NotifyFrontendSearchingResources notifies the user that there are no
    resources available and will be in a near future
    """
    return notifier.NotifyFrontendSearchingResourcesResponse()


@app.route("/guest", methods=["POST"])
@api.validate(resp=Response(HTTP_200=notifier.NotifyGuestResponse))
def notify_guest(json: notifier.NotifyGuestRequest):
    """
    NotifyGuest sends a QMP notification to the user desktop
    """
    return notifier.NotifyGuestResponse()
