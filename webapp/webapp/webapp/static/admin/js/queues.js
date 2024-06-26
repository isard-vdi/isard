/*
 *   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
 *   Copyright (C) 2023 Josep Maria Viñolas Aqueuer, Alberto Larraz Dalmases
 *
 *   This program is free software: you can redistribute it and/or modify
 *   it under the terms of the GNU Affero General Public License as published by
 *   the Free Software Foundation, either version 3 of the License, or
 *   (at your option) any later version.
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *   GNU Affero General Public License for more details.
 *
 *   You should have received a copy of the GNU Affero General Public License
 *   along with this program.  If not, see <https://www.gnu.org/licenses/>.
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

$(document).ready(function () {

    queues_table = $('#queues').DataTable({
        "ajax": {
            "url": "/api/v3/queues",
            "dataSrc": ""
        },
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "columns": [
            {
                "data": "id",
            },
            {
                "data": "queued",
            },
            {
                "data": "started",
            },
            {
                "data": "finished",
            },
            {
                "data": "failed",
            },
            {
                "data": "deferred",
            },
            {
                "data": "scheduled",
            },
            {
                "data": "canceled",
            }
        ],
        "order": [[1, "asc"], [2, "desc"]],
    });

    consumerstable = $('#consumers').DataTable({
        "ajax": {
            "url": "/api/v3/queues/consumers",
            "dataSrc": ""
        },
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "columns": [
            {
                "data": "id"
            },
            {
                "data": "queue",
            },
            {
                "data": "priority",
            },
            {
                "data": "priority_id",
            },
            {
                "data": "subscribers",
            },
            {
                "data": "status",
            },
        ],
        "order": [[1, "asc"], [2, "desc"]],
    });
    // $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
})
