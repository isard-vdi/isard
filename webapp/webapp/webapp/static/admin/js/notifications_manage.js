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
    renderNotificationsDatatable();
    addTemplatePreviewListener("#modalNotification");
    handleTriggerDisplayOptions("#modalNotification");

    $('.btn-add-notification').on('click', function () {
        var modal = "#modalNotification";
        $(modal + " #enabled").iCheck('checked').iCheck('update');
        $(modal + " #force_accept").iCheck('unchecked').iCheck('update');
        setupNotificationModal(modal, "add", "fa fa-plus");
        resetTemplateDropdown(modal, function () { $(modal + " #template_id").trigger('change'); });
        resetActionDropdown(modal, function () { $(modal + " #action_id").val("custom") });
        $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
    });

    $("#modalNotification #send").on('click', function () {
        var modal = "#modalNotification";
        var form = $(modal + "Form");
        form.parsley().validate();
        if (form.parsley().isValid()) {
            var formData = form.serializeObject();
            data = formData;
            data["enabled"] = formData["enabled"] == "on";
            data["force_accept"] = formData["force_accept"] == "on";
            data["order"] = parseInt(formData["order"]);
            data["ignore_after"] = data["ignore_after"] ? data["ignore_after"] : null;
            data["keep_time"] = parseInt(formData["keep_time"]);
            data["order"] = parseInt(formData["order"]);

            if (data.operation === "edit") {
                delete data.operation;
                $.ajax({
                    url: `/api/v3/admin/notification/${data.id}`,
                    type: 'PUT',
                    contentType: 'application/json',
                    data: JSON.stringify(data),
                    success: function (xhr) {
                        $(modal).modal('hide');
                        new PNotify({
                            title: 'Notification updated',
                            text: 'Notification has been updated successfully',
                            type: 'success',
                            hide: true,
                            delay: 5000
                        });
                        $('#notifications-table').DataTable().ajax.reload();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR updating notification`,
                            text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        });
                    }
                });
            } else if (data.operation === "add") {
                delete data.operation;
                delete data.id;
                $.ajax({
                    url: '/api/v3/admin/notification',
                    type: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify(data),
                    success: function (xhr) {
                        $(modal).modal('hide');
                        new PNotify({
                            title: 'Notification added',
                            text: 'Notification has been added successfully',
                            type: 'success',
                            hide: true,
                            delay: 5000
                        });
                        $('#notifications-table').DataTable().ajax.reload();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR adding notification`,
                            text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        });
                    }
                });
            }
        }
    });

    $("#notifications-table").find('tbody').on('click', 'button', function () {
        var data = $(this).closest("table").DataTable().row($(this).parents('tr')).data();
        switch ($(this).attr('id')) {
            case "btn-edit":
                var modal = "#modalNotification";
                setupNotificationModal(modal, "edit", "fa fa-pencil");
                $(modal + " #id").val(data.id);
                $.ajax({
                    url: `/api/v3/admin/notification/${data.id}`,
                    type: 'GET',
                    success: function (notification) {
                        $(modal + " #name").val(notification.name);
                        $(modal + " #enabled").iCheck(notification.enabled ? 'check' : 'uncheck').iCheck('update');
                        $(modal + " #action_id").val(notification.action_id);
                        $(modal + " #trigger").val(notification.trigger);
                        $(modal + " #display").val(notification.display).trigger('change');
                        $(modal + " #force_accept").iCheck(notification.force_accept ? 'check' : 'uncheck').iCheck('update');
                        $(modal + " #order").val(notification.order);
                        $(modal + " #ignore_after").val(moment(notification.ignore_after).format('YYYY-MM-DDTHH:mm'));
                        $(modal + " #keep_time").val(notification.keep_time);
                        resetTemplateDropdown(modal, function () { $(modal + " #template_id").val(notification.template_id).trigger('change'); });
                        resetActionDropdown(modal, function () { $(modal + " #action_id").val(notification.action_id); });
                    }
                });
                $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
                break;
            case "btn-alloweds":
                modalAllowedsFormShow("notifications", data);
                break;
            case "btn-delete":
                new PNotify({
                    title: `Delete notification`,
                    text: `Do you really want to delete the logs associated with this notification?`,
                    hide: false, opacity: 0.9,
                    confirm: { confirm: true },
                    history: { history: false },
                    addclass: 'pnotify-center-large',
                    confirm: {
                        confirm: true,
                        buttons: [
                            {
                                text: 'Delete with logs', primary: true,
                                click: function (notice) {
                                    deleteNotification(data.id, true);
                                    notice.remove();
                                }
                            },
                            {
                                text: 'Delete without logs',
                                click: function (notice) {
                                    deleteNotification(data.id, false);
                                    notice.remove();
                                }
                            },
                            {
                                text: 'Cancel',
                                click: function (notice) {
                                    notice.remove();
                                }
                            }
                        ]
                      },
                });
                break;
        }
    });
});

function renderNotificationsDatatable() {
    $('#notifications-table').DataTable({
        "ajax": {
            url: '/api/v3/admin/notifications',
            type: 'GET',
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "searching": true,
        "footer": true,
        "order": [[6, "asc"]],
        "deferRender": true,
        "columns": [
            {
                data: 'name', title: 'Name', "render": function (data, type, full, meta) {
                    return data ? data : '-';
                }
            },
            { data: 'action_id', title: 'Action' },
            {
                data: 'compute', title: 'Compute', "render": function (data, type, full, meta) {
                    if (data) {
                        return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"></i>`
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
            },
            {
                data: 'display', title: 'Display', "render": function (data, type, full, meta) {
                    return data.join(', ');
                }
            },
            {
                data: 'force_accept', title: 'Force Accept', "render": function (data, type, full, meta) {
                    if (data) {
                        return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"></i>`
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
            },
            { data: 'item_type', title: 'Item Type' },
            { data: 'order', title: 'Order' },
            {
                data: 'template', title: 'Template', "render": function (data, type, full, meta) {
                    return data ? data : '-';
                }
            },
            {
                data: 'trigger', title: 'Trigger', "render": function (data, type, full, meta) {
                    return data ? data : '-';
                }
            },
            {
                data: 'enabled', title: 'Enabled', "render": function (data, type, full, meta) {
                    if (data) {
                        return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"></i>`
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
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
                data: 'keep_time', title: 'Keep Time', render: function (data) {
                    var weeks = data / 24 / 7;
                    return weeks % 1 === 0 ? weeks + " weeks" : weeks.toFixed(1) + " weeks";
                }
            },
            {
                data: null, title: 'Actions', width: '100px', "render": function (data, type, full, meta) {
                    let deleteButton = data.item_type !== "desktop" ? `<button title="Delete notification" class="btn btn-xs btn-danger" id="btn-delete" data-id="${data.id}"><i class="fa fa-trash"></i></button>` : '';
                    return `<button title="Edit notification" class="btn btn-xs btn-info" id="btn-edit" data-id="${data.id}"><i class="fa fa-pencil"></i></button>
                        <button title="Allowed users" class="btn btn-xs btn-primary" id="btn-alloweds" data-id="${data.id}"><i class="fa fa-users"></i></button>
                        ${deleteButton}`;
                }
            },
            {
                data: 'id', title: 'ID', "visible": false
            }
        ],
    });
    adminShowIdCol($('#notifications-table').DataTable());
}

function addTemplatePreviewListener(modal) {
    $(modal + " #template_id").on("change", function () {
        $(this).val()
        $.ajax({
            url: '/api/v3/admin/notifications/template/' + $(this).val(),
            type: 'GET',
            success: function (template) {
                var template_title = template.lang[template.default] ? template.lang[template.default].title : template.system.title;
                var template_body = template.lang[template.default] ? template.lang[template.default].body : template.system.body;

                $(modal + " #preview-panel").empty().html(`
                <h4>${template_title}</h4>
                <p>${template_body}</p>
                `).show();
            }
        });
    });
}

function setupNotificationModal(modal, operation, iconClass) {
    populateItemTypeSelect(modal, operation);

    var title = operation == "add" ? "Add Notification" : "Edit Notification";
    $(modal + " #modal-title").empty().text(title);
    $(modal + " #send-button-text").empty().text(title);
    $(modal + " .modal-title i").removeClass().addClass(iconClass);
    $(modal + "Form")[0].reset();
    $(modal + "Form").parsley().reset();
    $(modal + " #operation").val(operation);
    $(modal + " #trigger").trigger('change');
    $(modal + " #display").val("fullpage");
    
    $(modal + " #display").select2({
        "placeholder": " Select where to display the notification",
        "multiple": true,
        "dropDownParent": $(modal)
    });
}

function updateDisplayOptions(modal, trigger) {
    var displayOptions =
        // trigger ===  "login" ?  ["fullpage", "modal"] : ["fullpage", "modal", "bar", "guest", "mail"];
        ["fullpage"]

    $(modal + " #display").empty();
    $.each(displayOptions, function (_, option) {
        $(modal + " #display").append(new Option(option.charAt(0).toUpperCase() + option.slice(1), option));
    });
}

function handleTriggerDisplayOptions(modal) {
    $(modal + " #trigger").on('change', function () {
        updateDisplayOptions(modal, $(this).val());
    });
    updateDisplayOptions(modal);
}

function populateItemTypeSelect(modal, operation) {
    $(modal + " #item_type").empty();
    if (operation === "add") {
        $(modal + " #item_type").append(new Option("User", "user")).attr("disabled", false);
    } else if (operation === "edit") {
        var options = [
            "desktop", "desktops", "deployment", "deployments", "user"
        ];
        $.each(options, function (_, option) {
            $(modal + " #item_type").append(new Option(option.charAt(0).toUpperCase() + option.slice(1), option));
        });
        $(modal + " #item_type").attr("disabled", true);
    }
}

function deleteNotification(id, delete_logs) {
    $.ajax({
        type: 'DELETE',
        url: `/api/v3/admin/notification/${id}`,
        data: JSON.stringify({ "delete_logs": delete_logs }),
        contentType: "application/json",
        accept: "application/json",
        success: function (resp) {
            new PNotify({
                title: 'Deleted',
                text: `Notification deleted successfully`,
                hide: true,
                delay: 2000,
                opacity: 1,
                type: 'success'
            });
            $('#notifications-table').DataTable().row(`#${id}`).remove().draw();
        },
        error: function (data) {
            new PNotify({
                title: `ERROR deleting notification`,
                text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                type: 'error',
                hide: true,
                icon: 'fa fa-warning',
                delay: 5000,
                opacity: 1
            });
        }
    });
}

function resetTemplateDropdown(modal, callback) {
    $(modal + " #template_id").empty();
    $.ajax({
        url: '/api/v3/admin/notifications/templates',
        type: 'GET',
        success: function (data) {
            $.each(data, function (_, template) {
                $(modal + " #template_id").append(new Option(template.name, template.id));
            });
            callback();
        }
    });
}

function resetActionDropdown(modal, callback) {
    $(modal + " #action_id").empty();
    $.ajax({
        url: '/api/v3/admin/notification/actions/all',
        type: 'GET',
        success: function (data) {
            $.each(data, function (_, action) {
                $(modal + " #action_id").append(`<option value="${action.id}" title="${action.description}">${action.id}</option>`);
            });
            callback();
        }
    });
}