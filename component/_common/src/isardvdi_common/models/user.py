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

from cachetools import cached
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
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


# Resolving "which category does this user belong to" is one of the hottest
# reads in the product: every storage task produce does it, and so does every
# SocketIO fan-out, which means once per stream entry per consumer. Measured on
# a 25-VU burst: 29741 keyed reads of ``users`` for at most 25 distinct answers,
# 5.5 per settled entry.
#
# It is also the cheapest thing in the world to cache — a user's category is
# administrative data that changes by hand, and the only consequence of a stale
# answer is which SocketIO room an event is fanned to for up to the TTL.
_category_cache = SynchronizedTTLCache(maxsize=4096, ttl=60)


@cached(_category_cache)
def category_of(user_id):
    """The user's category, or ``None`` when the user is gone.

    One round trip, not two: ``User.get`` already answers "absent" with
    ``None``, so the ``exists`` probe that ``User(user_id)`` would run first
    carries no information.
    """
    if not user_id:
        return None
    try:
        owner = User.get(user_id)
    except Exception:
        return None
    return owner.get("category") if owner else None


class User(RethinkCustomBase):
    """
    Manage Domain Objects

    Use constructor with keyword arguments to create new Domain Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Domain Object.
    """

    _rdb_table = "users"
