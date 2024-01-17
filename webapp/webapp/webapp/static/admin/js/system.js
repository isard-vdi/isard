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

    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on);


});

function socketio_on() { }