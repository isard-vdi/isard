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
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid
from time import sleep


def mail(address: list, subject: str, text: str, html: str):
    message = MIMEMultipart("alternative")
    message["Message-ID"] = make_msgid()
    message["Subject"] = subject
    message["From"] = os.environ.get("NOTIFY_EMAIL_USERNAME")
    message["To"] = ", ".join(address)

    part1 = MIMEText(text, "plain", "utf-8")
    part2 = MIMEText(html, "html", "utf-8")
    message.attach(part1)
    message.attach(part2)

    server = smtplib.SMTP(
        os.environ.get("NOTIFY_EMAIL_SMTP_SERVER"),
        os.environ.get("NOTIFY_EMAIL_SMPT_PORT"),
    )
    server.starttls()
    server.login(
        os.environ.get("NOTIFY_EMAIL_USERNAME"), os.environ.get("NOTIFY_EMAIL_PASSWORD")
    )
    server.sendmail(message["from"], address, message.as_string())
    server.quit()
    sleep(5)
