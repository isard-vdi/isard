/*
*   Copyright © 2024 Pau Abril
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
    checkOldEntriesAction();

    $("#maxtime").on("change", function () {
        var max_time = ($(this).val());
        $.ajax({
            type: "PUT",
            url: "/api/v3/logs_desktops/config/old_entries/max_time/" + max_time,
            accept: "application/json",
        }).done(() => {
            new PNotify({
                title: "Updated time",
                text: `Actions will be performed after ${max_time} hours`,
                hide: true,
                delay: 1000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
            });
        }).fail(function (data) {
            new PNotify({
                title: "ERROR updating time",
                text: data.responseJSON.description,
                hide: true,
                delay: 1000,
                icon: 'fa fa-error',
                opacity: 1,
                type: 'error'
            });
        });
    });

    $("#btn-delete-logs").on("click", function () {
        new PNotify({
            title: "Are you sure you want to delete all logs data?",
            text: `This action is irreversible and can be resource-demanding.`,
            addclass: 'pnotify-center-large',
            confirm: {
                confirm: true,
                buttons: [
                    {
                        text: 'Delete', click: function (notice) {
                            $.ajax({
                                type: "DELETE",
                                url: "/api/v3/logs_desktops/old_entries/delete/all",
                                accept: "application/json",
                            }).done(() => {
                                new PNotify({
                                    title: "Deleting logs...",
                                    text: `All user logs are being deleted`,
                                    hide: false,
                                    delay: 1000,
                                    icon: 'fa fa-spinner fa-pulse',
                                    opacity: 1,
                                    type: 'success'
                                });
                            }).fail(function (data) {
                                new PNotify({
                                    title: "ERROR deleting logs",
                                    text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
                                    hide: true,
                                    delay: 1000,
                                    icon: 'fa fa-error',
                                    opacity: 1,
                                    type: 'error'
                                });
                            });
                            notice.remove();
                        }
                    },
                    {
                        text: 'Cancel', click: function (notice) {
                            notice.remove();
                        }
                    }
                ]
            },
        });
    });

    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on);
});


function toggleOldEntriesAction(action) {
    $.ajax({
        type: "PUT",
        url: "/api/v3/logs_desktops/config/old_entries/action/" + action,
        accept: "application/json",
    }).done(() => {
        updateSchedulerJob(action);
    });
}

function checkOldEntriesAction() {
    $.ajax({
        type: "GET",
        url: "/api/v3/logs_desktops/config/old_entries",
        accept: "application/json",
    }).done(function (oldEntriesConfig) {
        $('#archive-delete_wrapper input[name="archive-delete-action"][value="' + oldEntriesConfig.action + '"]').prop("checked", true).iCheck('update')
        $('#archive-delete_wrapper input[name="archive-delete-action"]').on("ifChecked", function () {
            toggleOldEntriesAction($(this).val());
        });
        $('#archive-delete_wrapper input[name="archive-delete-action"]').on("ifUnchecked", function () {
            toggleOldEntriesAction('none');
        });

        // $('#archive-delete_wrapper input[name="archive-delete-action"][value="' + oldEntriesConfig.action + '"]').prop("checked", true).iCheck('update')
        // $('#archive-delete_wrapper input[name="archive-delete-action"]').on("ifChecked", function () {
        //     toggleOldEntriesAction($(this).val());
        // });
        $('#maxtime').val(oldEntriesConfig.max_time);
    });
}

function updateSchedulerJob(action) {
    $.ajax({
        type: "PUT",
        url: "/scheduler/logs_desktops/old_entries/" + action,
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
            var max_time = $("#maxtime").val();
            new PNotify({
                title: "Updated scheduler",
                text: `Old entries will be ${action}d after ${max_time} hours`,
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