#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2023 Simó Albert i Beltran
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

from time import sleep

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

RETRY_INTERVAL = 5


class RedisRetry(Redis):
    def execute_command(self, *args, **kwargs):
        while True:
            try:
                return super().execute_command(*args, **kwargs)
            except (ConnectionError, RedisConnectionError) as exception:
                print(
                    f"Redis Connection Error: {exception} Retrying in {RETRY_INTERVAL} secconds",
                    flush=True,
                )
                sleep(RETRY_INTERVAL)
