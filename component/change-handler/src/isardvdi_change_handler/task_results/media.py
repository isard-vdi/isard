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

"""Media-side task_results handlers ported from core_worker.

``handle_recycle_bin_update`` is the migration of the apiv4-mediated
``recycle_bin_update`` callback into change-handler. It calls
``isardvdi_common.helpers.recycle_bin.RecycleBinHelpers.update_task_status``
directly — the same function the apiv4 endpoint ultimately called
through ``RecycleBinService.update_task``. No HTTP hop, no apiv4
dependency for this transition.
"""

import logging as log

from isardvdi_common.helpers.recycle_bin import Helpers as RecycleBinHelpers
from isardvdi_common.models.media import Media

from . import storage as task_results_storage

# Register Media for storage.handle_update_status dispatch. Done at
# import time so update_status payloads with ``"media": [...]`` resolve
# without storage.py needing to import media.py.
task_results_storage.register_item_class("media", Media)


def handle_media_update(task, **media_dict):
    """Port of core_worker.task.media_update.

    Either a direct call with ``media_dict`` (writes once) or an
    indirect call that walks the task's ``check_media_existence`` /
    ``download_url`` dependency results and applies each one.
    """
    if task.depending_status != "finished":
        return
    if media_dict:
        Media.init_document(**media_dict)
        return
    for dependency in task.dependencies:
        if dependency.task in ("check_media_existence", "download_url"):
            handle_media_update(task, **(dependency.result or {}))


def handle_recycle_bin_update(task, **recycle_bin_dict):
    """Port of core_worker.task.recycle_bin_update.

    core_worker walked ``task.dependency.dependency`` to find the
    storage worker task whose status to attribute. In change-handler we
    have the dependent task directly — its ``dependency.dependency``
    walk is the same one core_worker did via
    ``Task(get_current_job().dependency.dependency.id)``.

    Calls :meth:`RecycleBinHelpers.update_task_status` directly rather
    than going through the apiv4 HTTP endpoint that used to wrap it.
    """
    recycle_bin_id = recycle_bin_dict.get("recycle_bin_id")
    if not recycle_bin_id:
        log.warning(
            "task_results.recycle_bin_update: missing recycle_bin_id in payload"
        )
        return
    # core_worker did Task(get_current_job().dependency.dependency.id) to walk
    # two RQ links back to the chain root. change-handler runs *as* the
    # dependent task, so its own first dependency is what was
    # ``dependency.dependency`` from core_worker's POV.
    dependencies = task.dependencies
    if not dependencies:
        log.warning(
            "task_results.recycle_bin_update: task %s has no dependencies",
            task.id,
        )
        return
    root_dependencies = dependencies[0].dependencies
    if not root_dependencies:
        log.warning(
            "task_results.recycle_bin_update: task %s parent has no dependencies",
            task.id,
        )
        return
    root = root_dependencies[0]
    RecycleBinHelpers.update_task_status(
        {
            "recycle_bin_id": recycle_bin_id,
            "id": root.id,
            "status": root.status,
        }
    )
