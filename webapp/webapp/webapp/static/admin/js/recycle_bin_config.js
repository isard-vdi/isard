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
