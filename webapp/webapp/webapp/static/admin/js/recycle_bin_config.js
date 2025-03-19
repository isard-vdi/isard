/*
*   Copyright © 2024 Naomi Hidalgo
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
    checkDefaultDelete();
    checkDeleteAction();
    renderUnusedItemTimeoutsDatatable();

    $('#unused-desktops-table').find('tbody').on('click', 'button', function () {
        var data = $(this).closest("table").DataTable().row($(this).parents('tr')).data();
        switch ($(this).attr('id')) {
            case "btn-edit":
                var modal = "#modalUnusedTime";
                renderModal(modal, "edit");
                $.ajax({
                    type: 'GET',
                    url: `/api/v3/recycle_bin/unused_item_timeout_rule/${data.id}`,
                    contentType: 'application/json',
                    success: function (data) {
                        $(modal + ' #id').val(data.id);
                        $(modal + ' #name').val(data.name);
                        $(modal + ' #description').val(data.description);
                        $(modal + ' #op').val(data.op);
                        if (data.cutoff_time) {
                            $(modal + ' #cutoff_time').val(data.cutoff_time);
                        }
                        $(modal + ' #priority').val(data.priority);
                    }
                });
                $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
                break;
            case "btn-delete":
                new PNotify({
                    title: 'Confirmation Needed',
                    text: `Are you sure you want to delete rule "${data.name}"?`,
                    hide: false, opacity: 0.9, confirm: { confirm: true },
                    buttons: { closer: false, sticker: false },
                    addclass: 'pnotify-center'
                }).get().on('pnotify.confirm', function () {
                    $.ajax({
                        type: 'DELETE',
                        url: `/api/v3/recycle_bin/unused_item_timeout_rule/${data.id}`,
                        contentType: 'application/json',
                        success: function () {
                            new PNotify({
                                title: 'Deleted',
                                text: `Rule deleted successfully`,
                                hide: true,
                                delay: 2000,
                                opacity: 1,
                                type: 'success'
                            });
                            $('#unused-desktops-table').DataTable().row('#' + data.id).remove().draw();
                        },
                        error: function (data) {
                            new PNotify({
                                title: `ERROR deleting "${data.name}"`,
                                text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
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
            case "btn-alloweds":
                modalAllowedsFormShow("unused_item_timeout", data);
                break;
        }
    });

    $('.btn-add-unused-desktop-rule').on('click', function () {
        var modal = "#modalUnusedTime";
        renderModal(modal, "add");
        $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
    });

    $("#modalUnusedTime #send").on("click", function () {
        var form = $('#modalUnusedTimeForm');
        var data = form.serializeObject();
        var pk = data.id;
        delete data.id;
        data.cutoff_time = data.cutoff_time != "null" ? parseInt(data.cutoff_time) : null;
        data.priority = parseInt(data.priority)

        form.parsley().validate();
        if (form.parsley().isValid()) {
            if ($(this).data("action") == "edit") {
                $.ajax({
                    type: 'PUT',
                    url: `/api/v3/recycle_bin/unused_item_timeout_rule/${pk}`,
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function () {
                        $('form').each(function () { this.reset() });
                        $('.modal').modal('hide');
                        new PNotify({
                            title: 'Updated',
                            text: `Rule updated successfully`,
                            hide: true,
                            delay: 2000,
                            opacity: 1,
                            type: 'success'
                        });
                        $('#unused-desktops-table').DataTable().ajax.reload().draw();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR updating rule`,
                            text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        });
                    }
                });
            } else if ($(this).data("action") == "add") {
                delete data["id"];
                $.ajax({
                    type: 'POST',
                    url: '/api/v3/recycle_bin/unused_item_timeout_rules/',
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function () {
                        $('form').each(function () { this.reset() });
                        $('.modal').modal('hide');
                        new PNotify({
                            title: 'Added',
                            text: `Rule added successfully`,
                            hide: true,
                            delay: 2000,
                            opacity: 1,
                            type: 'success'
                        });
                        $('#unused-desktops-table').DataTable().ajax.reload().draw();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR adding rule`,
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

    $("#maxtime").on("change", function () {
        var max_time = ($(this).val());
        $.ajax({
            type: "PUT",
            url: "/api/v3/recycle_bin/config/old_entries/max_time/" + max_time,
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

});


function toggleOldEntriesAction(action) {
    $.ajax({
        type: "PUT",
        url: "/api/v3/recycle_bin/config/old_entries/action/" + action,
        accept: "application/json",
    }).done(() => {
        updateSchedulerJob(action);
    });
}

function checkOldEntriesAction() {
    $.ajax({
        type: "GET",
        url: "/api/v3/recycle_bin/config/old_entries",
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
        url: "/scheduler/recycle_bin/old_entries/" + action,
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

function toggleDefaultDelete(set) {
    $.ajax({
        type: "PUT",
        url: "/api/v3/recycle_bin/config/default-delete",
        accept: "application/json",
        data: JSON.stringify({
            'rb_default': set
        }),
        contentType: "application/json",
    }).done(() => {
        new PNotify({
            title: "Send to recycle bin by default " + (set ? 'enabled' : 'disabled'),
            text: "",
            hide: true,
            delay: 1000,
            icon: 'fa fa-success',
            opacity: 1,
            type: 'success'
        });
    })
}

function checkDefaultDelete() {
    $.ajax({
        type: "GET",
        url: "/api/v3/recycle_bin/config/default-delete",
        accept: "application/json",
    }).done(function (defaultDelete) {
        $("#default-delete-checkbox").iCheck(defaultDelete ? "check" : "uncheck").iCheck('update');

        $("#default-delete-checkbox").on("ifChecked", function () {
            toggleDefaultDelete(true);
        });
        $("#default-delete-checkbox").on("ifUnchecked", function () {
            toggleDefaultDelete(false);
        });
    });
}

function toggleDeleteAction(action) {
    $.ajax({
        type: "PUT",
        url: "/api/v3/recycle_bin/config/delete-action/" + action,
        accept: "application/json",
    }).done(() => {
        new PNotify({
            title: "Delete action set to " + action,
            text: "",
            hide: true,
            delay: 1000,
            icon: 'fa fa-success',
            opacity: 1,
            type: 'success'
        });
    }).fail(function (data) {
        new PNotify({
            title: "ERROR",
            text: data.responseJSON.description,
            type: 'error',
            hide: true,
            icon: 'fa fa-warning',
            delay: 5000,
            opacity: 1
        });
    });
}

function checkDeleteAction() {
    $.ajax({
        type: "GET",
        url: "/api/v3/recycle_bin/config/delete-action/",
        accept: "application/json",
    }).done(function (deleteAction) {
        $('#default-action_wrapper input[name="deleted-action"][value="' + deleteAction + '"]').prop("checked", true).iCheck('update')
        $('#default-action_wrapper input[name="deleted-action"]').on("ifChecked", function () {
            toggleDeleteAction($(this).val());
        });
    }).fail(function (data) {
        new PNotify({
            title: "ERROR",
            text: data.responseJSON.description,
            type: 'error',
            hide: true,
            icon: 'fa fa-warning',
            delay: 5000,
            opacity: 1
        });
    });
}

function renderUnusedItemTimeoutsDatatable() {
    $('#unused-desktops-table').DataTable({
        "ajax": {
            url: '/api/v3/recycle_bin/unused_item_timeout_rules',
            type: 'GET',
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "searching": true,
        "footer": true,
        "order": [[4, "desc"]],
        "deferRender": true,
        "columns": [
            { data: 'name', title: 'Name' },
            { data: 'description', title: 'Description' },
            { data: 'op', title: 'Operation' },
            {
                data: 'cutoff_time',
                title: 'Cutoff Time',
                render: function (data) {
                    if (data) {
                        return data + ' months';
                    } else {
                        return 'Never';
                    }
                }
            },
            { data: 'priority', title: 'Priority' },
            {
                data: null,
                title: 'Action',
                render: function (data) {
                    return `
                        <button title="Edit rule" class="btn btn-xs btn-info" id="btn-edit" data-id="${data.id}"><i class="fa fa-pencil"></i></button>
                        <button title="Allowed users" class="btn btn-xs btn-primary" id="btn-alloweds" data-id="${data.id}"><i class="fa fa-users"></i></button>
                        <button title="Delete rule" class="btn btn-xs btn-danger" id="btn-delete" data-id="${data.id}"><i class="fa fa-trash"></i></button>
                    `;
                }
            }
        ]
    });
}
function renderModal(modal, action) {
    $(modal + 'Form')[0].reset();
    $(modal + 'Form').parsley().reset();
    $(modal + ' :checkbox').iCheck('uncheck').iCheck('update');
    const options = [
        "send_unused_desktops_to_recycle_bin",
        "send_unused_deployments_to_recycle_bin"
    ];
    $(modal + "Form #op").empty().append(options.map(value => `<option value="${value}">${value.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())}</option>`).join(''));

    if (action == "edit") {
        $(modal + " .modal-header h4").html('<i class="fa fa-pencil fa-1x"></i> <i class="fa fa-hourglass-o"></i> Edit unused items rules');
        $(modal + " .modal-footer #send").html("Edit Rule").data("action", action);
        $(modal).addClass("editModal").removeClass("addModal");
    } else if (action == "add") {
        $(modal + " .modal-header h4").html('<i class="fa fa-plus fa-1x"></i> <i class="fa fa-hourglass-o"></i> Add unused items rules');
        $(modal + " .modal-footer #send").html("Add Rule").data("action", action);
        $(modal).addClass("addModal").removeClass("editModal");
    }
}
