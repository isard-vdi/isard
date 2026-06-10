#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2024 Josep Maria Viñolas Auquer
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Literal, Optional, Union
from uuid import uuid4

from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from pydantic import BaseModel, Field
from rethinkdb import r

from ..schemas.shared.quotas import Quota
from ..schemas.user import USER_ROLE, UserStorageModel


class UserModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    accessed: float | None = None
    active: bool = True
    email: str | None = None
    email_verified: Union[bool, int] = False
    email_verification_token: str | None = None
    group: str
    secondary_groups: list[str] = []
    password_history: list[str] = []
    password_last_updated: int
    name: str
    category: str
    description: str | None = None
    password: str
    start_logs_id: str | None = None
    photo: str | None = None
    provider: Literal["local", "ldap", "saml", "google"]
    role: USER_ROLE
    username: str
    uid: str
    quota: Union[Quota, Literal[False]] = False
    default_templates: list[str] | None = None
    vpn: dict | None = None
    user_storage: Optional[UserStorageModel] = None
    bastion_ssh_key: str | None = None


class User(RethinkCustomBase):
    """
    Manage Domain Objects

    Use constructor with keyword arguments to create new Domain Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Domain Object.
    """

    _rdb_table = "users"
