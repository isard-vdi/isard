/*
*    Copyright © 2026 Naomi Hidalgo Piñar
*
*    This file is part of IsardVDI.
*
*    IsardVDI is free software: you can redistribute it and/or modify
*    it under the terms of the GNU Affero General Public License as published by
*    the Free Software Foundation, either version 3 of the License, or (at your
*    option) any later version.
*
*    IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
*    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
*    FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
*    details.
*
*    You should have received a copy of the GNU Affero General Public License
*    along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
*
*  SPDX-License-Identifier: AGPL-3.0-or-later
*/

function refreshLogoPreviews() {
    var cacheBust = new Date().getTime();
    $("#preview-logo img").attr("src", "/api/v4/logo?t=" + cacheBust);
    $("#preview-logo_collapsed img").attr("src", "/api/v4/logo-collapsed?t=" + cacheBust);
}

function refreshLogoStatus() {
    $.ajax({
        url: "/api/v4/admin/item/logo",
    }).done((data) => {
        var logoCustom = data.logo && data.logo.enabled;
        var collapsedCustom = data.logo_collapsed && data.logo_collapsed.enabled;
        $("#logo-status-alert").text((logoCustom || collapsedCustom) ? "Using a custom logo" : "Using the default logos");

        var usingGeneral = logoCustom && !collapsedCustom;
        $("#preview-logo_collapsed img").toggle(!usingGeneral);
        $("#logo_collapsed-using-general").toggle(usingGeneral);
    })
}

$(document).ready(() => {
    refreshLogoStatus();
    refreshLogoPreviews();

    $("#form-system-logo input[name='logo[enabled]']").on("ifChanged", function () {
        toggleFormSection($(".system-logo-settings"), $(this).is(":checked"))
    }).trigger("ifChanged");

    $("#form-system-logo input[name='logo_collapsed[enabled]']").on("ifChanged", function () {
        toggleFormSection($(".system-logo_collapsed-settings"), $(this).is(":checked"))
    }).trigger("ifChanged");

    $("#btn-edit-logo").on("click", () => {
        $.ajax({
            url: "/api/v4/admin/item/logo",
        }).done((data) => {
            fillFormData($("#form-system-logo"), data);
            var cacheBust = new Date().getTime();
            if (data.logo && data.logo.enabled) {
                $(".system-logo-settings .file-content-preview").html('<img src="/api/v4/logo?t=' + cacheBust + '">').show()
            }
            if (data.logo_collapsed && data.logo_collapsed.enabled) {
                $(".system-logo_collapsed-settings .file-content-preview").html('<img src="/api/v4/logo-collapsed?t=' + cacheBust + '">').show()
            }
            $("#modal-system-logo").modal({
                backdrop: "static",
                keyboard: false
            }).modal("show");
        })
    })

    $("#modal-system-logo").on("hidden.bs.modal", function () {
        resetFormData($(this).find("form"));
    })

    $("#system-logo-save").on("click", () => {
        var data = collectFormData($("#form-system-logo"))
        var notice = new PNotify({
            title: "Logo",
            text: "Saving logo configuration...",
            icon: "fa fa-spinner fa-pulse"
        });
        $.ajax({
            type: "PUT",
            url: "/api/v4/admin/item/logo",
            data: JSON.stringify(data),
            contentType: "application/json"
        }).fail((data) => {
            notice.update({
                title: "ERROR saving logo configuration",
                text: data.responseJSON.description,
                type: "error",
                icon: "fa fa-warning",
                delay: 15000
            });
        }).done(() => {
            $(".modal").modal("hide")
            notice.update({
                text: "Saved successfully",
                icon: null,
                type: "success",
                delay: 2000
            });
            refreshLogoStatus();
            refreshLogoPreviews();
        })
    })
})
