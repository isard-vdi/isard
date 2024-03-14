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

    // Maintenance
    maintenance_update_checkbox = (enabled) => {
        let status;
        if (enabled) {
            status = "check"
        } else {
            status = "uncheck"
        }
        $("#maintenance_checkbox").iCheck(status);
    }
    maintenance_bind_checkbox = () => {
        $("#maintenance_checkbox").on("ifChecked", () => {
            maintenance_update_status(true);
        })
        $("#maintenance_checkbox").on("ifUnchecked", () => {
            maintenance_update_status(false);
        })
    }
    maintenance_update_status = (enabled) => {
        $("#maintenance_wrapper").hide();
        $("#maintenance_spinner").show();
        $("#maintenance_checkbox").unbind("ifChecked");
        $("#maintenance_checkbox").unbind("ifUnchecked");
        $.ajax({
            type: "PUT",
            url: "/api/v3/maintenance",
            data: JSON.stringify(enabled),
            contentType: "application/json",
            accept: "application/json",
        }).done((data) => {
            maintenance_update_checkbox(data);
            maintenance_bind_checkbox();
            $("#maintenance_spinner").hide();
            $("#maintenance_wrapper").show();
        })
    }
    $.ajax({
        type: "GET",
        url: "/api/v3/maintenance",
        accept: "application/json",
    }).done((data) => {
        maintenance_update_checkbox(data);
        maintenance_bind_checkbox();
        $("#maintenance_spinner").hide();
        $("#maintenance_wrapper").show();
    })

    enable_maintenance_text_bind_checkbox = () => {
        $("#enable-maintenance-text-checkbox").on("ifChecked", () => {
            enable_maintenance_update_status(true);
        })
        $("#enable-maintenance-text-checkbox").on("ifUnchecked", () => {
            enable_maintenance_update_status(false);
        })
    }


    enable_maintenance_update_status = (enabled) => {
        $.ajax({
            type: "PUT",
            url: "/api/v3/maintenance/text/enable/" + enabled,
            accept: "application/json",
        }).done(() => {
            new PNotify({
                title: "Set to " + (enabled ? 'enabled' : 'disabled'),
                text: "",
                hide: true,
                delay: 1000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
            });
            enabled ? $("#preview-panel").removeClass("disabled-preview") : $("#preview-panel").addClass("disabled-preview");
        }).fail(function (data) {
            new PNotify({
                title: `ERROR ${(enabled ? 'enabling' : 'disabling')} custom maintenance text`,
                text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                type: 'error',
                hide: true,
                icon: 'fa fa-warning',
                delay: 5000,
                opacity: 1
            });
        });
    }

    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on);

    $("#btn-edit-maintenance-text").on("click", function () {
        var modal = "#modalEditMaintenanceText";
        $.ajax({
            url: "/api/v3/maintenance/text",
        }).done(function (data) {
            $(modal + " #title").val(data.title);
            $(modal + " #text").val(data.body);
        });
        $(modal).modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
    });

    $("#modalEditMaintenanceText #send").on("click", function () {
        var form = $('#modalEditMaintenanceTextForm');
        data = form.serializeObject();
        form.parsley().validate();
        $.ajax({
            type: "PUT",
            url: "/api/v3/maintenance/text",
            contentType: 'application/json',
            data: JSON.stringify(data)
        }).done(function (data) {
            new PNotify({
                title: 'Updated',
                text: `Maintenance text successfully`,
                hide: true,
                delay: 2000,
                opacity: 1,
                type: 'success'
            });
            $('.modal').modal('hide');
            showMaintenanceText();
        }).fail(function (data) {
            new PNotify({
                title: `ERROR editing maintenance text`,
                text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                type: 'error',
                hide: true,
                icon: 'fa fa-warning',
                delay: 5000,
                opacity: 1
            });
        });
    });

    showMaintenanceText();

});

function socketio_on() { }

function showMaintenanceText(div) {
    $.ajax({
        url: "/api/v3/maintenance/text",
    }).done(function (data) {
        $("#preview").text(`${data.title}\n\n${data.body}`)
        $("#enable-maintenance-text-checkbox").iCheck(data.enabled ? "check" : "uncheck").iCheck('update');
        data.enabled ? $("#preview-panel").removeClass("disabled-preview") : $("#preview-panel").addClass("disabled-preview");
    });
    enable_maintenance_text_bind_checkbox();
}

