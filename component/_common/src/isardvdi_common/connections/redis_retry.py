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

import logging
from time import sleep

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

log = logging.getLogger(__name__)

RETRY_INTERVAL = 5

# A retry loop with no end is only acceptable while it is visible. Past this
# many attempts the same command has been failing for long enough to be an
# outage rather than a blip, and the log has to say so at a level someone alerts
# on.
LOUD_AFTER_ATTEMPTS = 3


class RedisRetry(Redis):
    """A client that waits a redis outage out instead of failing the command.

    Retrying for ever is the point: the storage workers are started with this
    class so that a redis restart does not kill them mid-chain.
    """

    def execute_command(self, *args, **kwargs):
        attempts = 0
        while True:
            try:
                return super().execute_command(*args, **kwargs)
            except (
                ConnectionError,
                RedisConnectionError,
                RedisTimeoutError,
            ) as exception:
                attempts += 1
                # A TimeoutError is the client's own socket deadline, not a lost
                # connection, and calling both "connection error" sends whoever
                # reads this after a network problem that is not there.
                log.log(
                    (
                        logging.ERROR
                        if attempts >= LOUD_AFTER_ATTEMPTS
                        else logging.WARNING
                    ),
                    "%s on %s (attempt %s), retrying in %ss: %s",
                    type(exception).__name__,
                    args[0] if args else "?",
                    attempts,
                    RETRY_INTERVAL,
                    exception,
                )
                sleep(RETRY_INTERVAL)
