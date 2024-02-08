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


    user_policy_table = $('#users-password-policy').DataTable({
        "ajax": {
            "url": "/api/v3/admin/authentication/policies/local",
            "type": 'GET',
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
            { "data": "category_name" },
            {
                "data": "role", "render": function (data, type, row) {
                    return (data ? data : "all")
                }
            },
            {
                "data": "email_verification",
                "render": function (data, type, full, meta) {
                    if (data) {
                        return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"></i>`
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
            },
            {
                "data": "disclaimer",
                "render": function (data, type, full, meta) {
                    if (data) {
                        return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"></i>`
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
            },
            { "data": "password.digits" },
            { "data": "password.length" },
            { "data": "password.lowercase" },
            { "data": "password.uppercase" },
            { "data": "password.special_characters" },
            {
                "data": "password.expiration"
            },
            {
                "data": "password.old_passwords"
            },
            {
                "data": "password.not_username", "render": function (data, type, row) {
                    return (data == true ? '<i class="fa fa-check" style="color:lightgreen"></i>' : "-");
                }
            },
            {
                "data": null,
                "width": "70px",
                "render": function (data, type, row) {
                    buttons = '<button id="btn-edit-policy" class="btn btn-xs btn-edit" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>';
                    if (row.email_verification || row.disclaimer || row.password.expiration) {
                        buttons += '<button id="btn-policy-force" class="btn btn-xs" type="button" data-placement="top" title="Force verification at login"><i class="fa fa-repeat" style="color:darkblue"></i></button>'
                    }
                    if (!((row.category_name == "all") && (row.role == "all"))) {
                        buttons += `<button id="btn-policy-delete" class="btn btn-xs" type="button" data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button>`;
                    }
                    return buttons
                }
            },
            { "data": "id", "visible": false }
        ],
    });
    adminShowIdCol(user_policy_table);

    $('.btn-add-policy').on('click', function () {
        var modal = '#modalPolicyAdd';
        $(modal + "Form #scope select").empty();
        $(modal + " #category").select2({
            dropdownParent: $(modal),
        });

        $(modal + ' .disclaimer-cb').iCheck('uncheck').iCheck('update');
        $(modal + " #template-content").hide();
        populateTextTemplateSelect(modal);
        $(modal + " .disclaimer-template").val("null");

        $(modal).modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');

        $.ajax({
            type: "GET",
            url: "/api/v3/admin/categories",
            async: false,
            cache: false,
            success: function (category) {
                $(modal + ' #category-select select').append('<option selected value="all">ALL</option>');
                showHideContent($('#modalPolicyAdd #disclaimer-content'), true);
                showHideContent($('#modalPolicyAdd #disclaimer-warning'), false);
                $.each(category, function (key, value) {
                    $(modal + ' #category-select select').append(
                        `<option value="${value.id}">${value.name}</option>`
                    );
                });
            }
        })

        $.ajax({
            type: "GET",
            url: "/api/v3/admin/roles",
            async: false,
            cache: false,
            success: function (role) {
                $(modal + ' #role-select select').append('<option selected value="all">ALL</option>');
                $.each(role, function (key, value) {
                    $(modal + ' #role-select select').append(
                        `<option value="${value.id}">${value.name}</option>`
                    )
                });
            }
        })
    });


    $('#modalPolicyAdd #send').on('click', function (e) {
        const formData = $('#modalPolicyAddForm').serializeObject();
        $('#modalPolicyAddForm').parsley().validate();
        var data = formData;
        if ($('#modalPolicyAddForm').parsley().isValid()) {
            if (formData['disclaimer-cb'] == 'on' && !formData['disclaimer-template']) {
                new PNotify({
                    title: `ERROR enabling disclaimer`,
                    text: 'If disclaimer acknowledgement is enabled, a text template must be selected',
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            } else {
                data = {
                    'category': data["category"],
                    'role': data["role"],
                    'type': "local",
                    "password": {
                        'digits': parseInt(data['digits']),
                        'expiration': parseInt(data['expiration']),
                        'length': parseInt(data['length']),
                        'lowercase': parseInt(data['lowercase']),
                        'old_passwords': parseInt(data['old_passwords']),
                        'uppercase': parseInt(data['uppercase']),
                        'special_characters': parseInt(data['special_characters']),
                        'not_username': data['not_username'].toLowerCase() === 'true',
                    },
                    'email_verification': data['verification-cb'] == 'on',
                    'disclaimer': data['disclaimer-cb'] != 'on' && data['category'] !== "all" ? false :
                        {
                            'template': data['disclaimer-template']
                        }
                };
                $.ajax({
                    type: 'POST',
                    url: `/api/v3/admin/authentication/policy/`,
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function (data) {
                        $('form').each(function () { this.reset() });
                        $('.modal').modal('hide');
                        user_policy_table.ajax.reload();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR adding user policy`,
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


    $('#modalPolicyAdd #policy-select select').on("change", function () {
        var policy = $('#modalPolicyAdd #policy-select select').val();
        $('#modalPolicyAdd .policy_fields').hide();
        $(`#modalPolicyAdd #${policy}_fields`).show();
    });

    $('#local_panel').find(' tbody').on('click', 'button', function () {
        var data = $(this).closest("table").DataTable().row($(this).parents('tr')).data();
        if ($(this).attr('id') == 'btn-policy-delete') {
            new PNotify({
                title: `Delete user policy`,
                text: `Do you really want to delete user policy for category "${data.category_name}" and role "${data.role}"`,
                hide: false,
                opacity: 0.9,
                confirm: { confirm: true },
                buttons: { closer: false, sticker: false },
                history: { history: false },
                addclass: 'pnotify-center'
            }).get().on('pnotify.confirm', function () {
                $.ajax({
                    type: 'DELETE',
                    url: `/api/v3/admin/authentication/policy/${data.id}`,
                    accept: "application/json",
                    success: function (resp) {
                        new PNotify({
                            title: 'Deleted',
                            text: `Policy deleted successfully`,
                            hide: true,
                            delay: 2000,
                            opacity: 1,
                            type: 'success'
                        });
                        user_policy_table.ajax.reload();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR deleting user policy`,
                            text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        });
                    }
                });
            });
        } else if ($(this).attr('id') == 'btn-policy-force') {
            var modal = "#modalForceVerification";
            if (data.password.expiration) { $(modal + " #force-password").show() } else { $(modal + " #force-password").hide() }
            if (data.email_verification) { $(modal + " #force-email").show() } else { $(modal + " #force-email").hide() }
            if (data.disclaimer) { $(modal + " #force_disclaimer").show() } else { $(modal + " #force_disclaimer").hide() }

            $(modal + " h5 #span-category").html(data.category_name);
            $(modal + " h5 #span-role").html(data.role);

            $(modal + " .modal-body .btn").data("role", data.role)
            $(modal + " .modal-body .btn").data("category_name", data.category_name)
            $(modal + " .modal-body .btn").data("id", data.id)
            $(modal).modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');

        } else if ($(this).attr('id') == 'btn-edit-policy') {
            var modal = '#modalPolicyEdit';
            $(modal + " #id").val(data.id);
            $(modal + " #category").append(
                `<option selected value="${data.category}">${data.category_name}</option>`
            );
            showHideContent($(modal + " #disclaimer-content"), data.category == "all");
            showHideContent($(modal + " #disclaimer-warning"), data.category != "all");

            populateTextTemplateSelect(modal);
            $.ajax({
                type: "GET",
                url: "/api/v3/admin/roles",
                async: false,
                cache: false,
                success: function (role) {
                    $(modal + ' #role-select select').append('<option selected value="all">ALL</option>');
                    $.each(role, function (key, value) {
                        $(modal + ' #role-select select').append(
                            `<option value="${value.id}">${value.name}</option>`
                        )
                    });
                }
            });
            $(modal + " #role").val(data.role);
            $.ajax({
                type: "GET",
                url: `/api/v3/admin/authentication/policy/${data.id}`,
                success: function (policy) {
                    $(modal + " #digits").val(policy.password.digits);
                    $(modal + " #expiration").val(policy.password.expiration);
                    $(modal + " #length").val(policy.password["length"]);
                    $(modal + " #lowercase").val(policy.password.lowercase);
                    $(modal + " #not_username").val(String(policy.password.not_username));
                    $(modal + " #old_passwords").val(policy.password.old_passwords);
                    $(modal + " #special_characters").val(policy.password.special_characters);
                    $(modal + " #uppercase").val(policy.password.uppercase);
                    if (policy.email_verification) {
                        $(modal + ' #verification-cb').iCheck('check').iCheck('update');
                    } else {
                        $(modal + ' #verification-cb').iCheck('uncheck').iCheck('update');
                    }
                    if (policy.disclaimer) {
                        $(modal + ' .disclaimer-cb').iCheck('check').iCheck('update');
                        $(modal + " #template-content").show();
                        $(modal + ' .disclaimer-template').val(policy.disclaimer.template).trigger("change");
                    } else {
                        $(modal + ' .disclaimer-cb').iCheck('uncheck').iCheck('update');
                        $(modal + " #template-content").hide();
                    }
                }
            })
            $(modal).modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
        };
    });


    $('#modalPolicyEdit #send').on('click', function (e) {
        var modal = '#modalPolicyEditForm';
        const formData = $(modal).serializeObject();
        $(modal).parsley().validate();
        if ($('#modalPolicyEditForm').parsley().isValid()) {
            if (formData['disclaimer-cb'] == 'on' && !formData['disclaimer-template']) {
                new PNotify({
                    title: `ERROR enabling disclaimer`,
                    text: 'If disclaimer acknowledgement is enabled, a text template must be selected',
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            } else {
                var data = {
                    'type': 'local',
                    'password': {
                        'digits': parseInt(formData['digits']),
                        'expiration': parseInt(formData['expiration']),
                        'length': parseInt(formData['length']),
                        'lowercase': parseInt(formData['lowercase']),
                        'old_passwords': parseInt(formData['old_passwords']),
                        'uppercase': parseInt(formData['uppercase']),
                        'special_characters': parseInt(formData['special_characters']),
                        'not_username': formData['not_username'].toLowerCase() === 'true',
                    },
                    'email_verification': formData['verification-cb'] == 'on',
                    'disclaimer': formData['disclaimer-cb'] != 'on' && formData['category'] !== "all" ? null :
                        {
                            'template': formData['disclaimer-template']
                        }
                };
    
                $.ajax({
                    type: 'PUT',
                    url: `/api/v3/admin/authentication/policy/${formData.id}`,
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function (data) {
                        $('form').each(function () { this.reset() });
                        $('.modal').modal('hide');
                        user_policy_table.ajax.reload();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR editing policy`,
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

    $("#modalForceVerification .modal-body .btn").on("click", function () {
        var data = $(this).data();
        new PNotify({
            title: `Force ${data.policy}?`,
            text: `Do you really want to force ${data.policy} for all users in category "${data.category_name}" and role "${data.role}" at login?`,
            hide: false,
            opacity: 0.9,
            confirm: { confirm: true },
            buttons: { closer: false, sticker: false },
            history: { history: false },
            addclass: 'pnotify-center'
        }).get().on('pnotify.confirm', function () {
            $.ajax({
                type: 'PUT',
                url: `/api/v3/admin/authentication/force_validate/${data.policy}/${data.id}`,
                accept: "application/json",
                success: function (resp) {
                    new PNotify({
                        title: 'Deleted',
                        text: `Policy forced successfully`,
                        hide: true,
                        delay: 2000,
                        opacity: 1,
                        type: 'success'
                    });
                    user_policy_table.ajax.reload();
                },
                error: function (data) {
                    new PNotify({
                        title: `ERROR forcing user policy`,
                        text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    });
                }
            });
        });
    });

    $('#modalPolicyAdd #category').on('change', function () {
        showHideContent($('#modalPolicyAdd #disclaimer-content'), $('#category').val() == "all");
        showHideContent($("#modalPolicyAdd #disclaimer-warning"), $('#category').val() != "all");
    });
    $('.disclaimer-cb').on('ifChanged', function () {
        showHideContent(
            $(this).closest('#disclaimer_fields').find("#template-content"),
            $(this).iCheck('update')[0].checked
        );
    });
    $('.disclaimer-template').on('change', function () {
        $.ajax({
            url: "/api/v3/admin/notifications/template/" + $(this).val(),
            type: "GET"
        }).then(template => {
            $(this).siblings("#preview-panel")
                .empty()
                .html(`
                    <div class='x_title'>
                        <b>${template.lang[template.default].title}</b>
                    </div>
                    <div class='clearfix'></div>
                    ${template.lang[template.default].body}
                    <hr>
                    ${template.lang[template.default].footer}
                `).show();
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

function populateTextTemplateSelect(modal) {
    $(modal + " .disclaimer-template").empty().append(
        "<option value='null' disabled>-- Select a template --</option>"
    );
    $(modal + " #preview-panel").hide();

    $.ajax({
        url: "/api/v3/admin/notifications/templates",
        type: "GET"
    }).then(response => {
        $(modal + " #template-content p").hide();
        $.each(response, function (key, template) {
            if (!["password", "email"].includes(template.kind)) {
                $(modal + " .disclaimer-template").append(`
                        <option value="${template.id}">${template.name}</option>
                    `);
            }
        });
        if ($(modal + " .disclaimer-template").children().length <= 1) {
            $(modal + " #template-content p").show();
        } else { $(modal + " #template-content p").hide(); }
    });
}