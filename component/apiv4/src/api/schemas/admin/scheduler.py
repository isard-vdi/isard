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

from typing import Optional

from pydantic import BaseModel, Field


class SchedulerSystemJob(BaseModel):
    """One row of ``GET /admin/scheduler/jobs/system``.

    Plucked from the ``scheduler_jobs`` table by
    ``AdminSchedulerService.get_system_jobs``.
    """

    id: str
    name: Optional[str] = None
    kind: Optional[str] = None
    next_run_time: Optional[float] = Field(
        default=None,
        description="UTC epoch seconds — the apiv3 contract returned a float here",
    )


class SchedulerBookingsJob(SchedulerSystemJob):
    """One row of ``GET /admin/scheduler/jobs/bookings``.

    Same shape as ``SchedulerSystemJob`` plus the ``kwargs`` blob the
    bookings scheduler stores per job.
    """

    kwargs: Optional[dict] = None
