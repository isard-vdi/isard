#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Simó Albert i Beltran
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

import sys

from fastapi import Request
from isardvdi_common.helpers.error_base import ErrorBase
from rethinkdb.connection_pool import PoolClosedError, PoolExhaustedError


class Error(ErrorBase):
    @classmethod
    async def create(cls, request: Request, *args, **kwargs) -> "Error":
        # When the active exception is a pool-control signal
        # (saturation or shutdown) re-raise the original instead of
        # wrapping it. The dedicated apiv4 exception handlers map
        # those to 503 with a structured payload — wrapping them as
        # ``internal_server`` would surface the same wire shape as
        # genuine query failures and lose the actionable signal
        # (raise pool size / a stuck connection is holding the pool
        # open). Routes still call this from
        # ``except Exception: raise await Error.create(...)``; the
        # re-raise propagates out of the awaited coroutine through
        # the outer ``raise`` and lands at the global handler.
        exc_type, exc_value, _ = sys.exc_info()
        if exc_value is not None and isinstance(
            exc_value, (PoolExhaustedError, PoolClosedError)
        ):
            raise exc_value
        return cls(
            *args, custom_request=request, request_body=await request.body(), **kwargs
        )
