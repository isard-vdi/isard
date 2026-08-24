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

#: Tasks whose FINAL payload is worth persisting. Only a download's is: it
#: carries ``total_bytes``, the measured on-disk size that quota, analytics and
#: the usage pipeline sum.
#:
#: ``move`` is deliberately absent. Its payload is only
#: ``{total_percent, received_percent}`` (docker/storage/task/task.py), so once
#: the transfer is over the final write would leave every template row carrying
#: a permanent ``{100, 100}`` that no reader ever looks at — every consumer of
#: template progress is guarded on ``status == CreatingTemplate``, which by then
#: is false. It still moves the row's status on; it just stores nothing.
_PERSISTS_FINAL = ("download_url", "download_url_for_domain")

#: Statuses a row may be in while its download is queued but not yet running.
#: Seeing progress proves curl is running, so the row is moved on. Anything
#: else is left alone — an abort or a failure must not be overwritten by a
#: tick that was already in flight.
_STARTING_STATUSES = ("DownloadStarting",)

#: Status a row reaches once progress proves the transfer is running.
_RUNNING_STATUS = "Downloading"


def apply_row_progress(task_id, final=False):
    """Persist what survives the transfer, and only that.

    ``final`` is True for the ``result`` entry, which carries the closing
    flush, and False for every intermediate tick.

    An INTERMEDIATE percentage never reaches the database. It is a transient the
    next tick supersedes, it had no durability contract even before this — the
    progress consumer ACKs unconditionally whether the write landed or not —
    and it was costing a hard write per tick, which on a long copy is a hundred
    fsyncs to move a bar. The frontend already receives it live from the task
    event and degrades cleanly without the column: the card passes ``undefined``
    for the bar when the row carries no progress and simply does not draw one,
    so a page loaded mid-operation shows the row with its real status and gains
    the bar on the next tick.

    The FINAL flush is a different thing wearing the same name and it MUST be
    written. Its ``total_bytes`` is the exact on-disk size the worker measured,
    and it is what every media-space reader sums — quota
    (``lib/usage/media.py``), analytics (``lib/analytics/analytics.py``) and the
    media listing all pluck it straight out of ``progress``. Dropping it would
    leave the database disagreeing with the disk, which is the one thing this
    write is for.

    The status transition stays on both paths, because that is state and not
    progress: without it a download sits at ``DownloadStarting`` for its whole
    life. It is written once — the first tick that finds the row still starting
    — so an intermediate tick costs one read and, after that first one, no
    write at all.

    Returns True when the row was written.
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

    # The tick still has to SAY the transfer is running, so an empty progress
    # payload is nothing to act on.
    progress = (task.job.meta or {}).get(ROW_PROGRESS_META_KEY)
    if not progress:
        return False

    model = _ITEM_CLASS_MAP.get(item_class)
    if model is None:
        log.warning("row_progress: no model registered for %s", item_class)
        return False

    try:
        # ``build`` and not ``exists`` + construct: one read, and None for a row
        # deleted while its download was still running rather than a raise.
        row = model.build(item_id)
        if row is None:
            return False
        starting = row.status in _STARTING_STATUSES
        persists = final and task.task in _PERSISTS_FINAL
        if not (starting or persists):
            # An intermediate tick on a row that has already moved on: nothing
            # to write, which is the steady state of a running transfer.
            return False
        # A row on its way out (aborting, failed, deleting) keeps its status —
        # a tick already in flight must not resurrect a cancelled download.
        if starting:
            row.status = _RUNNING_STATUS
        if final and task.task in _PERSISTS_FINAL:
            row.progress = progress
    except Exception:
        log.exception("row_progress: failed to write %s %s", item_class, item_id)
        return False

    return True
