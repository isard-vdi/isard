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

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from time import sleep

from isardvdi_common.api_rest import ApiRest


def mail(address: list, subject: str, text: str, html: str):
    smtp = ApiRest("isard-api").get("/smtp")
    if not smtp.get("enabled"):
        raise Exception("SMTP not enabled")
    message = MIMEMultipart("alternative")
    message["Date"] = formatdate()
    message["Message-ID"] = make_msgid(domain=smtp.get("host"))
    message["Subject"] = subject
    message["From"] = smtp.get("username")
    message["To"] = ", ".join(address)

    part1 = MIMEText(text, "plain", "utf-8")
    part2 = MIMEText(html, "html", "utf-8")
    message.attach(part1)
    message.attach(part2)

    server = smtplib.SMTP(smtp.get("host"), smtp.get("port"))
    server.starttls()
    server.login(smtp.get("username"), smtp.get("password"))
    server.sendmail(message["from"], address, message.as_string())
    server.quit()
