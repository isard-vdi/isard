/*
*   Copyright © 2025 Naomi Hidalgo
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
    populateStatusSelect();
    $notification_logs_detail = $(".notifications-logs-detail");

    $("#btn-delete-all-data").on('click', function () {
        new PNotify({
            title: `Delete all notification data`,
            text: `Are you sure you want to delete all notification data?`,
            hide: false, opacity: 0.9,
            confirm: { confirm: true },
            history: { history: false },
            addclass: 'pnotify-center-large',
            buttons: {
                closer: false,
                sticker: false
            },
            addclass: 'pnotify-center'
        }).get().on('pnotify.confirm', function () {
            $.ajax({
                type: 'DELETE',
                url: `/api/v3/admin/notifications/data`,
                contentType: 'application/json',
                success: function (data) {
                    new PNotify({
                        title: 'Deleted',
                        text: `Notification data deleted successfully`,
                        hide: true,
                        delay: 2000,
                        opacity: 1,
                        type: 'success'
                    });
                    $("#notifications-users-table").DataTable().clear().draw();
                    $('#status').empty();
                },
                error: function (data) {
                    new PNotify({
                        title: `ERROR deleting notification data`,
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    });
                }
            });
        }).on('pnotify.cancel', function () { });
        });
});

function populateStatusSelect() {
    var statusSelect = $('#status');
    $('#status').empty();
    $.ajax({
        url: '/api/v3/admin/notifications/statuses',
        type: 'GET',
        success: function (statuses) {
            statusSelect.empty();
            statusSelect.append('<option value="none" disabled selected> -- Select a notification status --</option>');
            statuses.forEach(function (status) {
                statusSelect.append(`<option value="${status}">${status}</option>`);
            });
        },
        error: function (error) {
            statusSelect.append('<option value="none" disabled selected> -- No data available --</option>');
        }
    });
    $('#status').on('change', (event) => {
        renderNotificationUsersDatatable($('#status').val());
    })
}

function renderNotificationsLogsDatatable(table, status, user_id) {
    table.DataTable({
        "ajax": {
            url: '/api/v3/admin/notifications/data/' + status + "/" + user_id,
            type: 'GET',
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "searching": true,
        "footer": true,
        "order": [[2, "asc"]],
        "deferRender": true,
        "columns": [
            {
                data: 'notification_name', title: 'Notification'
            }, {
                data: 'item_type', title: 'Notification'
            },
            {
                data: 'ignore_after', title: 'Ignore After', render: function (data) {
                    if (!data || moment(data).isBefore('1970-01-01')) {
                        return "-";
                    }
                    return `<span title="${moment(data).fromNow()}">${moment(data).format('DD-MM-YYYY HH:mm')}</span>`;
                }
            },
            {
                data: 'accepted_at', title: 'Accepted At', render: function (data) {
                    if (!data) {
                        return "-";
                    }
                    return `<span title="${moment(data).fromNow()}">${moment(data).format('DD-MM-YYYY HH:mm')}</span>`;
                }
            },
            {
                data: 'created_at', title: 'Created At', render: function (data) {
                    if (!data) {
                        return "-";
                    }
                    return `<span title="${moment(data).fromNow()}">${moment(data).format('DD-MM-YYYY HH:mm')}</span>`;
                }
            },
            {
                data: 'notified_at', title: 'Notified At', render: function (data) {
                    if (!data) {
                        return "-";
                    }
                    return `<span title="${moment(data).fromNow()}">${moment(data).format('DD-MM-YYYY HH:mm')}</span>`;
                }
            }, {
                data: "vars", title: "Vars", render: function (data) {
                    return Object.keys(data).map(key => `<strong>${key}</strong>: ${data[key]}`).join(', ');
                }
            },
            {
                data: null, title: 'Actions', render: function (data, type, full, meta) {
                    return '<button title="Delete notification" class="btn btn-xs btn-danger" id="btn-delete-notification-data" data-id="${data.id}"><i class="fa fa-trash"></i></button>';
                }
            },

            {
                data: 'id', title: 'ID', "visible": false
            }
        ],
        "fnInitComplete": function () {
            addDetailDeleteButtonListeners();
            adminShowIdCol($('#notifications-logs-table').DataTable());
        }
    });
}

function renderNotificationUsersDatatable(status) {
    $('#notifications-users-table').DataTable({
        "ajax": {
            url: '/api/v3/admin/notifications/data/user/' + status,
            type: 'GET',
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "item_id",
        "searching": true,
        "footer": true,
        "deferRender": true,
        "columns": [
            {
                "className": 'details-control',
                "orderable": false,
                "width": "10px",
                "data": null,
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { data: 'user_name', title: 'User' },
            { data: null, title: 'Notification status', render: function () { return status } },
            { data: 'notifications', title: 'Notifications' },
            {
                data: null, title: 'Actions', render: function () {
                    return '<button title="Delete notification" class="btn btn-xs btn-danger" id="btn-delete" data-id="${data.id}"><i class="fa fa-trash"></i></button>';
                }
            }
        ],
        "fnInitComplete": function () {
            notification_users_datatable = $(this).DataTable();
            $('#notifications-users-table tbody').on('click', 'td.details-control', function () {
                var tr = $(this).closest("tr");
                var row = notification_users_datatable.row(tr);
                if (row.child.isShown()) {
                    row.child.hide();
                    tr.removeClass("shown");
                } else {
                    if (notification_users_datatable.row('.shown').length) {
                        $('.details-control', notification_users_datatable.row('.shown').node()).click();
                    }
                    row.child(renderNotificationLogsDetailPannel(row.data())).show()
                    tr.addClass('shown');
                }
            });
            addDeleteButtonListeners();
        }
    });



}

function renderNotificationLogsDetailPannel(d) {
    $newPanel = $notification_logs_detail.clone();
    $newPanel.html(function () {
        renderNotificationsLogsDatatable($newPanel.find('#notifications-logs-table'), $('#status').val(), d.user_id);
        // return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description);
    });
    return $newPanel;
}


function addDeleteButtonListeners() {
    $("#notifications-users-table").find('tbody').on('click', 'button', function () {
        var data = $(this).closest("table").DataTable().row($(this).parents('tr')).data();
        switch ($(this).attr('id')) {
            case "btn-delete":
                new PNotify({
                    title: `Delete notification data`,
                    text: `Are you sure you want to delete this user's notification logs?`,
                    hide: false, opacity: 0.9,
                    confirm: { confirm: true },
                    history: { history: false },
                    addclass: 'pnotify-center-large',
                    buttons: {
                        closer: false,
                        sticker: false
                    },
                    addclass: 'pnotify-center'
                }).get().on('pnotify.confirm', function () {
                    $.ajax({
                        type: 'DELETE',
                        url: `/api/v3/admin/notifications/data/${data.user_id}`,
                        contentType: 'application/json',
                        success: function (data) {
                            new PNotify({
                                title: 'Deleted',
                                text: `Notification data deleted successfully`,
                                hide: true,
                                delay: 2000,
                                opacity: 1,
                                type: 'success'
                            });
                            $("#notifications-logs-table").DataTable().row('#' + data.id).remove().draw();
                        },
                        error: function (data) {
                            new PNotify({
                                title: `ERROR deleting notification data`,
                                text: data.responseJSON.description,
                                type: 'error',
                                hide: true,
                                icon: 'fa fa-warning',
                                delay: 5000,
                                opacity: 1
                            });
                        }
                    });
                }).on('pnotify.cancel', function () { });
                break;
        }
    });
}

function addDetailDeleteButtonListeners() {
    $("#notifications-logs-table").find('tbody').on('click', 'button', function () {
        var data = $(this).closest("table").DataTable().row($(this).parents('tr')).data();
        switch ($(this).attr('id')) {
            case "btn-delete-notification-data":
                new PNotify({
                    title: `Delete notification`,
                    text: `Are you sure you want to delete this notification?`,
                    hide: false, opacity: 0.9,
                    confirm: { confirm: true },
                    history: { history: false },
                    addclass: 'pnotify-center-large',
                    buttons: {
                        closer: false,
                        sticker: false
                    },
                    addclass: 'pnotify-center'
                }).get().on('pnotify.confirm', function () {
                    $.ajax({
                        type: 'DELETE',
                        url: `/api/v3/admin/notifications/data/${data.id}`,
                        contentType: 'application/json',
                        success: function (data) {
                            new PNotify({
                                title: 'Deleted',
                                text: `Notification deleted successfully`,
                                hide: true,
                                delay: 2000,
                                opacity: 1,
                                type: 'success'
                            });
                            $("#notifications-logs-table").DataTable().row('#' + data.id).remove().draw();
                        },
                        error: function (data) {
                            new PNotify({
                                title: `ERROR deleting notification`,
                                text: data.responseJSON.description,
                                type: 'error',
                                hide: true,
                                icon: 'fa fa-warning',
                                delay: 5000,
                                opacity: 1
                            });
                        }
                    });
                }).on('pnotify.cancel', function () { });
                break;
        }
    });
}