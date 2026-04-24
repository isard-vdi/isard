#
#   Copyright © 2025 Pau Abril Iranzo
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


import datetime
from uuid import uuid4

from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from pydantic import BaseModel, Field
from rethinkdb import r

from ..schemas.bookings import *


class BookingModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    item_id: str
    item_type: str
    start: datetime.datetime
    end: datetime.datetime
    title: str
    units: int
    user_id: str
    plans: list[Plan]
    reservables: Reservables


class Booking(RethinkCustomBase):

    _rdb_table = "bookings"
