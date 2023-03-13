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

from api.libv2.redis_base import RedisBase
from gevent import Greenlet
from rq import Worker as RqWorker
from rq.worker import StopRequested


class RqWorkerGreenlet(RqWorker):
    """
    Adapted RQ Worker to be stopped when run inside a greenlet
    """

    def _shutdown(self):
        """
        Intercept StopRequested exception from original method and send it to
        greenlet running the worker
        """
        try:
            super()._shutdown()
        except StopRequested as exception:
            self.greenlet.kill(exception=exception, block=False)

    def _install_signal_handlers(self):
        """
        Do not install signal handlers for handling SIGINT and SIGTERM gracefully.
        """
        pass


class Worker(RedisBase):
    """
    RQ Worker to process api queue.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.worker = RqWorkerGreenlet(["api"], connection=self._redis)
        self.worker.greenlet = Greenlet(self.worker.work)
        self.worker.greenlet.start()

    def stop(self):
        """
        Stop RQ Worker gracefully
        """
        self.worker.request_stop(None, None)
        self.worker.greenlet.join()
