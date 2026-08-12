#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
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

"""Persist the row progress a storage task leaves in its job metadata.

A storage worker runs where there is no database to write to: the ``storage``,
``hypervisor`` and ``hypervisor-standalone`` flavours each ship the storage part
without the database one, so a worker on any of those nodes cannot update the
media or domain row it is downloading into.

So the worker states the progress and this side persists it. The payload rides
in the job's own metadata, which the worker already writes on the same tick, and
the identity comes from the job's kwargs, which already name the row. Nothing
new travels on the stream: the ``progress`` event the worker publishes is
unchanged, and it is what brings us here.

Both halves degrade safely on their own. An old worker writes the row itself and
leaves no metadata, so this is a no-op; a new worker paired with an old consumer
keeps downloading and only the bar stops moving. Neither combination has to be
deployed before the other.
"""

import logging as log

from isardvdi_common.models.task import Task

from .storage import _ITEM_CLASS_MAP

#: Job metadata key the storage worker writes the row payload under.
ROW_PROGRESS_META_KEY = "row_progress"

#: Which task reports into which row, and the kwarg naming it. A task absent
#: from here never touches a row, so its metadata is ignored.
_ROW_OF_TASK = {
    "download_url": ("media", "media_id"),
    "download_url_for_domain": ("domain", "domain_id"),
    "move": ("domain", "progress_domain_id"),
}

#: Statuses a row may be in while its download is queued but not yet running.
#: Seeing progress proves curl is running, so the row is moved on. Anything
#: else is left alone — an abort or a failure must not be overwritten by a
#: tick that was already in flight.
_STARTING_STATUSES = ("DownloadStarting",)

#: Status a row reaches once progress proves the transfer is running.
_RUNNING_STATUS = "Downloading"


def apply_row_progress(task_id):
    """Write the progress the task left in its metadata onto its row.

    Called for every ``progress`` event. Returns True when a row was written,
    which the tests assert on; the consumer ignores it, because a tick that
    lands nowhere is not a failure worth retrying — the next one supersedes it.
    """
    try:
        task = Task(task_id)
    except Exception:
        log.exception("row_progress: failed to load Task(%s)", task_id)
        return False

    item_class, kwarg = _ROW_OF_TASK.get(task.task, (None, None))
    if not item_class:
        return False

    item_id = (task.kwargs or {}).get(kwarg)
    if not item_id:
        return False

    progress = (task.job.meta or {}).get(ROW_PROGRESS_META_KEY)
    if not progress:
        return False

    model = _ITEM_CLASS_MAP.get(item_class)
    if model is None:
        log.warning("row_progress: no model registered for %s", item_class)
        return False

    try:
        if not model.exists(item_id):
            # Deleted while its download was still running. Constructing the
            # model would raise, and init_document would insert it back as a
            # row holding nothing but an id and a progress dict.
            return False
        row = model(item_id)
        if row.status in _STARTING_STATUSES:
            row.status = _RUNNING_STATUS
        row.progress = progress
    except Exception:
        log.exception("row_progress: failed to write %s %s", item_class, item_id)
        return False

    return True
