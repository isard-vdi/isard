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
    renderTableNotificationTemplates();
    $template_detail = $(".notification-tmpl-detail");

    $('#notification-tmpls-table tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest("tr");
        var row = $('#notification-tmpls-table').DataTable().row(tr);
        var rowData = row.data();

        if (row.child.isShown()) {
            row.child.hide();
            tr.removeClass("shown");
        } else {
            row.child(rowData).show();
            row.child(addDetailPannel(row.data())).show();
            tr.addClass("shown");
        }
    });

    $("#modalNotificationTemplateForm #language").on("change", function () {
        changeBodyLanguage("#modalNotificationTemplateForm", $(this).val());
    });

    $('#modalNotificationTemplate #btn-preview').on("click", function () {
        togglePreviewMode("#modalNotificationTemplate", $(this).data("action") == "preview");
    });

    $('#modalNotificationTemplate #btn-apply').on("click", function () {
        applyMessage("#modalNotificationTemplate");
    });

    $('tbody').on('click', 'button', function () {
        var row = $(this).closest('table').DataTable().row($(this).closest('tr'));
        var rowData = row.data();
        var id = rowData.id;

        if ($(this).hasClass('btn-edit-notification-tmpl')) {
            var modal = "#modalNotificationTemplate";
            renderModal(modal, "edit");
            $.ajax({
                type: 'GET',
                url: `/api/v3/admin/notifications/template/${id}`,
                contentType: 'application/json',
                success: function (data) {
                    availableLanguages = Object.keys(data.lang)
                    language = data.default != "system" ?
                        data.default : Object.keys(data.lang)[0];
                    if (data.default == language) {
                        $(modal + " #default-lang").iCheck('check').iCheck('update');
                    } else {
                        $(modal + " #default-lang").iCheck('uncheck').iCheck('update');
                    }
                    populateLanguage(modal, availableLanguages)
                    $(modal + ' #id').val(id);
                    $(modal + ' #default').val(data.default);
                    $(modal + ' #name').val(data.name);
                    $(modal + ' #language').val(language);
                    $(modal + ' #description').val(data.description);
                    if (data.lang[language]) {
                        $(modal + ' #title').val(data.lang[language].title);
                        $(modal + ' #body').val(data.lang[language].body);
                        $(modal + ' #footer').val(data.lang[language].footer);
                    }
                    showParameters(modal, data.vars);
                }
            });
            $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
        }
    });

    $("#modalNotificationTemplate #send").on("click", function () {
        var form = $('#modalNotificationTemplateForm');
        var data = form.serializeObject();
        var pk = data.id;

        if (checkCleanHTML(data.body) && checkCleanHTML(data.footer)) {
            if (data["default-lang"] == "on") {
                data["default"] = data["language"]
            } else if (form.find("#default").val() == data["language"]) {
                data["default"] = "system";
            }
            form.parsley().validate();
            if (form.parsley().isValid()) {
                togglePreviewMode("#modalNotificationTemplate", false)
                if ($(this).data("action") == "edit") {
                    $.ajax({
                        type: 'PUT',
                        url: '/api/v3/admin/notifications/template/' + pk,
                        data: JSON.stringify(data),
                        contentType: "application/json",
                        success: function (data) {
                            $('form').each(function () { this.reset() });
                            $('.modal').modal('hide');
                            new PNotify({
                                title: 'Updated',
                                text: `Notification template updated successfully`,
                                hide: true,
                                delay: 2000,
                                opacity: 1,
                                type: 'success'
                            })
                            $('#notification-tmpls-table').DataTable().ajax.reload().draw();
                        },
                        error: function (data) {
                            new PNotify({
                                title: `ERROR updating notification template`,
                                text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                                type: 'error',
                                hide: true,
                                icon: 'fa fa-warning',
                                delay: 5000,
                                opacity: 1
                            })
                        }
                    });
                }
            }
        }
    });

});

function addDetailPannel(tmpl) {
    $newPanel = $template_detail.clone();
    $newPanel.find('#notification-tmpl\\.id').remove();
    $newPanel.find("#system_tmpl-title").html(tmpl.system.title);
    $newPanel.find("#system_tmpl-body").html(tmpl.system.body);
    $newPanel.find("#system_tmpl-footer").html("<hr>" + tmpl.system.footer);

    return $newPanel
}


function showParameters(modal, parameterList) {
    $.each(parameterList, function (key, value) {
        $(modal + " #notification-template-parameters").append(`
            <a class="list-group-item list-group-item-action" style="cursor:pointer"
            title="Click to copy to clipboard" data-placeholder="${value}" id="${key}">{${key}}</a>
        `);
        $(`${modal} #notification-template-parameters #${key}`).on("click", function () {
            navigator.clipboard.writeText(`{${key}}`);
            $(modal + " #body").focus();
            new PNotify({
                title: ` Copied to clipboard`,
                type: 'info',
                hide: true,
                icon: 'fa fa-clipboard',
                delay: 2000,
                opacity: 0.7
            });
        });
    });
}


function changeBodyLanguage(modal, language) {
    var modal = ".editModal";
    $.ajax({
        url: "/api/v3/admin/notifications/template/" + $(modal + " #id").val(),
        type: "GET",
        contentType: 'application/json',
        success: function (data) {
            if (data.lang[language]) {
                if (data.default == language) {
                    $(modal + " #default-lang").iCheck('check').iCheck('update');
                } else {
                    $(modal + " #default-lang").iCheck('uncheck').iCheck('update');
                }
                $(modal + " #title").val(data.lang[language].title);
                $(modal + " #body").val(data.lang[language].body);
                $(modal + " #footer").val(data.lang[language].footer);
            } else {
                $(modal + " #default-lang").iCheck('uncheck').iCheck('update');
                $(modal + " #title").val(data.system.title);
                $(modal + " #body").val(data.system.body);
                $(modal + " #footer").val(data.system.footer);
            }
            togglePreviewMode(modal, false);
        }
    });
}



function renderModal(modal, action) {
    $(modal + ' #notification-template-parameters').empty();
    $(modal + ' #language').empty();
    togglePreviewMode(modal, false);

    if (action == "edit") {
        $(modal + " .modal-header h4").html('<i class="fa fa-pencil fa-1x"></i> <i class="fa fa-edit"></i> Edit Notification Template');
        $(modal + " .modal-footer #send").html("Edit Notification Template").data("action", action);
        $(modal).addClass("editModal").removeClass("addModal")
    } else if (action == "add") {
        $(modal + " .modal-header h4").html('<i class="fa fa-plus fa-1x"></i> <i class="fa fa-edit"></i> Add Notification Template');
        $(modal + " .modal-footer #send").html("Add Notification Template");
        $(modal).addClass("addModal").removeClass("editModal");
    }
}


function populateLanguage(modal, availableLanguageList) {
    const languageList = {
        ca: 'Català',
        de: 'Deutsch',
        en: 'English',
        es: 'Castellano',
        eu: 'Euskara',
        fr: 'Français',
        pl: 'Polski',
        ru: 'Русский'
    }
    $(modal + ' #language').append("<option disabled selected>--Choose a Language--</option>");
    $.each(languageList, function (langCode, langName) {
        const optionName = availableLanguageList && availableLanguageList.includes(langCode) ? `${langName} (*)` : langName;
        $(modal + ' #language').append(`<option value=${langCode}>${optionName}</option>`);
    });
}


function renderTableNotificationTemplates() {
    notification_tmpls_table = $('#notification-tmpls-table').DataTable({
        "ajax": {
            "url": "/api/v3/admin/notifications/templates",
            "contentType": "application/json",
            "type": 'GET',
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "deferRender": true,
        "columns": [
            {
                "className": 'details-control',
                "orderable": false,
                "data": null,
                "defaultContent": `<button class="btn btn-xs btn-info"
                    type="button"  data-placement="top"><i class="fa fa-plus"
                    title="See system default template"></i></button>`
            },
            { "data": "name" },
            { "data": "description" },
            { "data": "default" },
            {
                "orderable": false,
                "data": null,
                "render": function (data, type, row) {
                    return `<button title="Edit notification template" class="btn btn-xs btn-info btn-edit-notification-tmpl" type="button" data-placement="top" ><i class="fa fa-pencil"></i></button>`;
                }
            },
        ],
    });
};


function togglePreviewMode(modal, preview) {
    var button = $(modal + " #btn-preview");
    if (preview) {
        if (checkCleanHTML($(modal + " #body").val()) && checkCleanHTML($(modal + " #footer").val())) {
            button.html(`<i class="fa fa-pencil"></i> Edit text`).data("action", "edit");
            previewText = $(modal + " #body").val();
            $.each($(modal + " #notification-template-parameters a"), function (key, value) {
                var parameter = $(value)
                previewText = previewText.replace(`{${parameter.attr("id")}}`, parameter.data("placeholder"));
            })

            $(modal + " #body").hide();
            $(modal + " #body-panel").removeClass("col-md-8");
            $(modal + " #body-preview").addClass("preview");
            $(modal + " #body-preview").empty().html(previewText).show();

            $(modal + " #footer").hide();
            $(modal + " #footer-wrapper label").hide();
            $(modal + " #footer-preview").empty().html("<hr>" + $(modal + " #footer").val()).show();

            $(modal + " #parameters-panel").hide();
        }
    } else {
        button.html(`<i class="fa fa-search"></i> Preview`).data("action", "preview");
        $(modal + " #body").show();
        $(modal + " #body-panel").addClass("col-md-8");
        $(modal + " #body-preview").hide();
        $(modal + " #body-preview").removeClass("preview");

        $(modal + " #footer").show();
        $(modal + " #footer-wrapper label").show();
        $(modal + " #footer-preview").hide();

        $(modal + " #parameters-panel").show();
    }
}

function applyMessage() {
    var form = $('#modalNotificationTemplateForm');
    var data = form.serializeObject();
    if (checkCleanHTML(data.body) && checkCleanHTML(data.footer)) {
        form.parsley().validate();
        if (form.parsley().isValid()) {
            togglePreviewMode('#modalNotificationTemplate', false)
            $.ajax({
                url: "/api/v3/admin/notifications/template/" + data.id,
                type: "PUT",
                data: JSON.stringify(data),
                contentType: 'application/json',
                success: function (data) {
                    new PNotify({
                        title: 'Updated',
                        text: `Language body updated successfully`,
                        hide: true,
                        delay: 2000,
                        opacity: 1,
                        type: 'success'
                    });
                    $("#language")
                },
                error: function (data) {
                    new PNotify({
                        title: `ERROR updating body`,
                        text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                }
            })
        }
    }
}

function checkCleanHTML(html) {
    if (
        html.indexOf("<script>") !== -1 ||
        html.indexOf("<iframe>") !== -1 ||
        html.indexOf("javascript:") !== -1
    ) {
        new PNotify({
            title: "Invalid html",
            text: "Scripts not allowed",
            type: "error",
            opacity: 0.9
        });
        return false;
    } else {
        return true;
    }
}