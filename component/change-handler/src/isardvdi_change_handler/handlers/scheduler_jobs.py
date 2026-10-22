#
#   Copyright © 2026 Josep Maria Viñolas Auquer
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

from .base import BaseHandler

SYSTEM_JOB_TYPE = "system"


def _job_type(val):
    value = getattr(val, "type", None)
    if value is not None:
        return value
    return (getattr(val, "additional_properties", None) or {}).get("type")


class SchedulerJobsHandler(BaseHandler):
    """Feeds the admin scheduler table with system jobs only."""

    async def on_insert(self, new_val):
        if _job_type(new_val) == SYSTEM_JOB_TYPE:
            await super().on_insert(new_val)

    async def on_update(self, old_val, new_val):
        if _job_type(new_val) == SYSTEM_JOB_TYPE:
            await super().on_update(old_val, new_val)

    async def on_delete(self, old_val):
        if _job_type(old_val) == SYSTEM_JOB_TYPE:
            await super().on_delete(old_val)
