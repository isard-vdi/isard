#
#   Copyright © 2025 IsardVDI
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

from smtplib import SMTP

from isardvdi_common.configuration import Configuration


class AdminSmtpService:

    @staticmethod
    def get_smtp_config() -> dict:
        return Configuration().smtp

    @staticmethod
    def update_smtp_config(data: dict) -> dict:
        Configuration().smtp = data
        return Configuration().smtp

    @staticmethod
    def get_smtp_enabled() -> bool:
        return Configuration().smtp.get("enabled", False)

    @staticmethod
    def test_smtp(configuration: dict) -> dict:
        try:
            with SMTP(
                configuration.get("host"), configuration.get("port")
            ) as connection:
                connection.starttls()
                connection.login(
                    configuration.get("username"), configuration.get("password")
                )
                connection.noop()
        except Exception as exception:
            return {"result": False, "error": str(exception)}
        return {"result": True}
