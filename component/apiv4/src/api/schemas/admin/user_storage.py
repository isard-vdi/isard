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

from typing import Any, Dict, Optional

from pydantic import BaseModel


class UserStorageAutoRegisterRequest(BaseModel):
    """Request for auto-registering a user storage provider"""

    domain: str
    user: str
    password: str
    intra_docker: bool
    verify_cert: bool


class UserStorageConnTestRequest(BaseModel):
    """Request for testing a user storage connection"""

    provider: str
    url: str
    urlprefix: str
    user: str
    password: str
    verify_cert: bool


class UserStorageAddRequest(BaseModel):
    """Request for adding a user storage provider"""

    provider: str
    name: str
    description: str
    url: str
    urlprefix: str
    access: str
    quota: Any
    verify_cert: bool
