#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Naomi Hidalgo Piñar
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


from enum import Enum
from typing import Optional

from pydantic import UUID4, BaseModel

from .bookings import Reservables
from .shared.hardware import GuestProperties, Hardware
from .shared.image import Image


class CreateDictDeployment(BaseModel):
    description: str
    guest_properties: GuestProperties
    hardware: Hardware
    image: Image
    name: str
    # Vue 3 deployments without a GPU pin omit ``reservables`` entirely;
    # the apiv4 ``CreateDesktopRequest.reservables`` is already
    # Optional but the deployment-internal ``create_dict[*].reservables``
    # was strict, so the route-side response model rejected the
    # legitimate ``None`` value with ``Input should be a valid
    # dictionary or instance of Reservables``.
    reservables: Optional[Reservables] = None
    template: str
    tag_desktop_id: UUID4


class UserPermissionsEnum(str, Enum):
    recreate = "recreate"
