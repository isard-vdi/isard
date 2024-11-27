/*
*   Copyright © 2023 Naomi Hidalgo
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
    $.ajax({
        type: "GET",
        url: "/api/v3/admin/authentication/providers",
        success: function (providers) {
            $.each(providers, function (key, provider) {
                if (provider) {
                    $(`#${key}-enabled`).css("color", "green")
                } else {
                    $(`#${key}_panel`).find('.x_content').css('display', 'none');
                    $(`#${key}_panel li`).find('i').toggleClass('fa-chevron-up fa-chevron-down');

                }
            });
        }
    })

});
