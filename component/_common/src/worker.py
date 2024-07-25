#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2024 Simó Albert i Beltran
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

from json import dumps

from rq import Worker


class Worker(Worker):
    """RQ Worker that report job duration"""

    def perform_job(self, *args, **kwargs):
        result = super().perform_job(*args, **kwargs)
        print(
            dumps(
                {
                    "job_id": args[0].id,
                    "user_id": args[0].meta.get("user_id"),
                    "queue": args[0].origin,
                    "task": args[0].func_name.rsplit(".", 1)[-1],
                    "job_args": args[0].args,
                    "job_kwargs": args[0].kwargs,
                    "duration": (args[0].ended_at - args[0].started_at).total_seconds(),
                }
            ),
            flush=True,
        )
        return result
