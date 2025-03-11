/*
*   Copyright © 2025 Pau Abril Iranzo
*
*   This file is part of IsardVDI.
*
*   IsardVDI is free software: you can redistribute it and/or modify
*   it under the terms of the GNU Affero General Public License as published by
*   the Free Software Foundation, either version 3 of the License, or (at your
*   option) any later version.
*
*   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
*   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
*   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
*   details.
*
*   You should have received a copy of the GNU Affero General Public License
*   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
*
* SPDX-License-Identifier: AGPL-3.0-or-later
*/


$(document).ready(function () {
    $('#registries').select2({
        placeholder: "Select statuses.",
        multiple: true,
        data: [
            { id: 'queued', text: 'queued' },
            { id: 'started', text: 'started' },
            { id: 'finished', text: 'finished' },
            { id: 'failed', text: 'failed' },
            { id: 'deferred', text: 'deferred' },
            { id: 'scheduled', text: 'scheduled' },
            { id: 'canceled', text: 'canceled' },
        ],
    });

    getConfig();


    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on);
});

function getConfig() {
    $.ajax({
        type: "GET",
        url: `/api/v3/queues/old_tasks/config`,
        contentType: 'application/json',
        success: function (data) {
            $('#registries').val(data.queue_registries).trigger('change');

            $('#maxtime').val(data.older_than / 60 / 60);

            $('#enabled-check').iCheck(data.enabled ? 'check' : 'uncheck').iCheck('update');
        },
        error: function ({ responseJSON: { description } = {} }) {
            const msg = description ? description : 'Something went wrong';
            new PNotify({
                title: "ERROR",
                text: msg,
                type: 'error',
                icon: 'fa fa-warning',
                hide: true,
                delay: 15000,
                opacity: 1
            });
        }
    });
}

$("#btn-update-config").on("click", function () {
    const selected_max_time = parseInt($('#maxtime').val()) * 60 * 60;
    if (!selected_max_time) {
        new PNotify({
            title: "ERROR",
            text: "Max time must be a number",
            type: 'error',
            icon: 'fa fa-warning',
            hide: true,
            delay: 15000,
            opacity: 1
        });
        return;
    }
    $.ajax({
        type: "PUT",
        url: `/api/v3/queues/old_tasks/config/max_time/${selected_max_time}`,
    })

    const selected_queue_registries = $('#registries').val();
    $.ajax({
        type: "PUT",
        url: `/api/v3/queues/old_tasks/config/queue_registries`,
        contentType: 'application/json',
        data: JSON.stringify({ queue_registries: selected_queue_registries }),
    })
});

$('#enabled-check').on("ifChecked", function () {
    $.ajax({
        type: "PUT",
        url: `/api/v3/queues/old_tasks/config/enabled`,
        contentType: 'application/json',
        data: JSON.stringify({ enabled: true }),
    })
    updateSchedulerJob("delete")
});
$('#enabled-check').on("ifUnchecked", function () {
    $.ajax({
        type: "PUT",
        url: `/api/v3/queues/old_tasks/config/enabled`,
        contentType: 'application/json',
        data: JSON.stringify({ enabled: false }),
    })
    updateSchedulerJob("none")
});

function updateSchedulerJob(action) {
    $.ajax({
        type: "PUT",
        url: "/scheduler/queues/old_tasks/" + action,
        accept: "application/json",
    }).done(function () {
        if (action === 'none') {
            new PNotify({
                title: "Updated scheduler",
                text: `Old entries action disabled`,
                hide: true,
                delay: 1000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
            });
        } else {
            new PNotify({
                title: "Updated scheduler",
                text: `Old entries will be ${action}d after hours`,
                hide: true,
                delay: 1000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
            });
        }
    }).fail(function (data) {
        new PNotify({
            title: "ERROR updating scheduler",
            text: data.responseJSON.description,
            hide: true,
            delay: 1000,
            icon: 'fa fa-error',
            opacity: 1,
            type: 'error'
        });
    });
}


// SOCKETIO

function socketio_on() {
    socket.on('logs_desktops_action', function (data) {
        PNotify.removeAll();
        var data = JSON.parse(data);
        if (data.status === 'failed') {
            new PNotify({
                title: `ERROR: ${data.action} on logs desktops.`,
                text: data.msg,
                hide: false,
                icon: 'fa fa-warning',
                opacity: 1,
                type: 'error'
            });
        } else if (data.status === 'completed') {
            new PNotify({
                title: `Action Succeeded: ${data.action}`,
                text: `The action "${data.action}" completed on logs desktops.`,
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
            });
        }
    });
}