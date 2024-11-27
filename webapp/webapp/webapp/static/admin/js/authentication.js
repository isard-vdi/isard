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
            $.each(providers, function (provider, enabled) {
                if (enabled) {
                    $(`#${provider}-enabled`).css("color", "green");
                    $(`#${provider}_panel li a.btn span`).show();
                    renderProviderDataTable(provider)
                } else {
                    $(`#${provider}_panel li.collapse`).find('i').toggleClass('fa-chevron-up fa-chevron-down');
                    $(`#${provider}_panel table`).hide();
                }
            });
        }
    })

    $('.btn-edit-config').on('click', function () {
        var modal = '#modalProviderConfig';
        var provider = $(this).data('provider');
        $(modal + " .modal-header #provider").empty().append(provider);
        $(modal + ' :checkbox').iCheck('uncheck').iCheck('update');
        $(modal + "Form #provider").val(provider);
        addProviderConfigModalListeners(modal);
        populateNotificationTemplate(modal);
        $.ajax({
            type: "GET",
            url: `/api/v3/authentication/provider/${provider}`,
            success: function (data) {
                data = data["migration"]
                $(`${modal} #import`).iCheck(data.import ? 'check' : 'uncheck').iCheck('update');
                $(`${modal} #export`).iCheck(data.export ? 'check' : 'uncheck').iCheck('update');
                $(`${modal} #notification_bar`).iCheck(data.notification_bar.enabled ? 'check' : 'uncheck').iCheck('update');
                $(`${modal} #action_after_migrate`).val(data.action_after_migrate);
                $(`${modal} #template`).val(data.notification_bar.template);
                $(`${modal} #level`).val(data.notification_bar.level);
                $(modal + " select#level").trigger("change");
            }
        });
        $(modal).modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
    });

    showAndHideByCheckbox($("#notification_bar"), $("#status_bar_notification"));

    $("#modalProviderConfig #send").on("click", function (e) {
        var formData = $("#modalProviderConfigForm").serializeObject();
        data = {"migration":{
            "provider": formData.provider,
            "notification_bar": {"enabled": formData.notification_bar == "on"}, 
            // "automigration": formData.allow_automigration == "on",
            "export": formData.export == "on",
            "import": formData.import == "on",
            "action_after_migrate": formData.action_after_migrate
        }};
        if (formData.notification_bar == "on") {
            data.migration.notification_bar.level = formData.level;
            data.migration.notification_bar.template = formData.template;
        }
        $.ajax({
            type: "PUT",
            url: `/api/v3/authentication/provider/${formData.provider}`,
            data: JSON.stringify(data),
            contentType: "application/json",
            success: function (data) {
                $("form").each(function () {
                    this.reset();
                });
                $(".modal").modal("hide");
                $("#" + formData.provider + "-table").DataTable().ajax.reload().draw();
            },
            error: function (data) {
                new PNotify({
                    title: `ERROR editing ${formData.provider} config`,
                    text: data.responseJSON
                        ? data.responseJSON.description
                        : "Something went wrong",
                    type: "error",
                    hide: true,
                    icon: "fa fa-warning",
                    delay: 5000,
                    opacity: 1,
                });
            },
        });
    });
});

function showHideContent(content, display) {
    if (display) {
        $(content).show();
    } else {
        $(content).hide();
    }
}


function populateNotificationTemplate(modal) {
    $(modal + " select#template").empty();
    $.ajax({
        url: "/api/v3/admin/notifications/templates",
        type: "GET"
    }).then(response => {
        $.each(response, function (key, template) {
            if (!["password", "email", "deleted_gpu"].includes(template.kind)) {
                $(modal + " select#template").append(`
                   <option selected value="${template.id}">${template.name}</option>
                `);
            }
        });
        $(modal + " select#template").trigger("change");

    });
}

function addProviderConfigModalListeners(modal) {
    $(modal + " select#template").off("change").on("change", function () {
        $.ajax({
            url: "/api/v3/admin/notifications/template/" + $(this).val(),
            type: "GET",
        }).then((template) => {
            $(modal + " #notification-preview")
                .empty()
                .html(
                    `<p>${template.lang[template.default].body}</p>`
                ).show();
            });
        });
        $(modal + " select#level").off("change").on("change", function () {
            $(modal + " #preview-panel").removeClass().addClass($(this).val())
        });
}

function renderProviderDataTable(provider) {
    $(`#${provider}-table`).DataTable({
        "ajax": {
            "url": `/api/v3/authentication/provider/${provider}`,
            "type": 'GET',
            "dataSrc": function (json) {
                return [json.migration];
            }
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "searching": false,
        "paging": false,
        "footer": false,
        "info": false,
        "deferRender": true,
        "columns": [
            { "data": "import",
                "render": function (data, type, full, meta) {
                    if (data) {
                        return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"></i>`
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
            },
            { "data": "export",
                "render": function (data, type, full, meta) {
                    if (data) {
                        return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"></i>`
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
             },
            { "data": "action_after_migrate" },
            {
                "data": "notification_bar.enabled",
                "render": function (data, type, full, meta) {
                    if (data) {
                        return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"></i>`
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
            },
            { "data": "notification_bar.template_name",
                "render": function (data, type, full, meta) {
                    if (full.notification_bar.enabled) {
                        return data
                    } else {
                        return '-'
                    }
                }
             },
            { "data": "notification_bar.level",
                "render": function (data, type, full, meta) {
                    if (full.notification_bar.enabled) {
                        return data
                    } else {
                        return '-'
                    }
                }
             },
        ],
    });
}