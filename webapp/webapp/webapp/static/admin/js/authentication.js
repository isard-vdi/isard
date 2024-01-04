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


    password_policy_table = $('#table-password-policy').DataTable({
        "ajax": {
            "url": "/api/v3/admin/authentication/policies/local/password",
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
            { "data": "digits" },
            { "data": "length" },
            { "data": "lowercase" },
            { "data": "uppercase" },
            { "data": "special_characters" },
            // { "data": "expire" },
            { "data": "old_passwords" },
            {
                "data": "not_username", "render": function (data, type, row) {
                    return (data == true ? '<i class="fa fa-check" style="color:lightgreen"></i>' : "-");
                }
            },
            {
                "data": null,
                "render": function (data, type, row) {
                    if (!((row.category_name == "all") && (row.role == "all"))) {
                        return `<button id="btn-edit-policy" class="btn btn-xs btn-edit" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>
                                <button id="btn-policy-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button>`;
                    } else {
                        return '<button id="btn-edit-policy" class="btn btn-xs btn-edit" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
                    }
                }
            },
            { "data": "id", "visible": false }
        ],
    });
    adminShowIdCol(password_policy_table);

    email_policy_table = $('#table-email-verification-policy').DataTable({
        "ajax": {
            "url": "/api/v3/admin/authentication/policies/local/email",
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
            { "data": "days" },
            {
                "data": null,
                "width": '10%',
                "render": function (data, type, row) {
                    if (!((row.category_name == "all") && (row.role == "all"))) {
                        return `<button id="btn-edit-policy" class="btn btn-xs btn-edit" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>
                                <button id="btn-policy-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button>`;
                    } else {
                        return '<button id="btn-edit-policy" class="btn btn-xs btn-edit" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
                    }
                }
            },
            { "data": "id", "visible": false }
        ],
    });
    adminShowIdCol(email_policy_table);

    $('.btn-add-policy').on('click', function () {
        var modal = '#modalPolicyAdd';
        $(modal + "Form #scope select").empty();
        $(modal + " #category").select2({
            dropdownParent: $(modal),
        });

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
        if (data.subtype == "password") {
            data = {
                'category': data["category"],
                'role': data["role"],
                'type': "local",
                'subtype': data["subtype"],
                'digits': parseInt(data['digits']),
                // 'expire': parseInt(data['expire']),
                'expire': 0,
                'length': parseInt(data['length']),
                'lowercase': parseInt(data['lowercase']),
                'old_passwords': parseInt(data['old_passwords']),
                'uppercase': parseInt(data['uppercase']),
                'special_characters': parseInt(data['special_characters']),
                'not_username': data['not_username'].toLowerCase() === 'true'
            };
        } else if (data.subtype == "email") {
            data = {
                'category': data["category"],
                'role': data["role"],
                'type': "local",
                'subtype': data["subtype"],
                'days': parseInt(data["days"])
            };
        }
        $.ajax({
            type: 'POST',
            url: `/api/v3/admin/authentication/policy/${data["subtype"]}`,
            data: JSON.stringify(data),
            contentType: "application/json",
            success: function (data) {
                $('form').each(function () { this.reset() });
                $('.modal').modal('hide');
                if (formData.subtype == "password") {
                    password_policy_table.ajax.reload();
                } else if (formData.subtype == "email") {
                    email_policy_table.ajax.reload();
                }
            },
            error: function (data) {
                new PNotify({
                    title: `ERROR adding ${formData.subtype} policy`,
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


    $('#modalPolicyAdd #policy-select select').on("change", function () {
        var policy = $('#modalPolicyAdd #policy-select select').val();
        $('#modalPolicyAdd .policy_fields').hide();
        $(`#modalPolicyAdd #${policy}_fields`).show();
    });

    $('#local_panel').find(' tbody').on('click', 'button', function () {
        var data = $(this).closest("table").DataTable().row($(this).parents('tr')).data();
        if ($(this).attr('id') == 'btn-policy-delete') {
            new PNotify({
                title: `Delete ${data.subtype} policy`,
                text: `Do you really want to delete ${data.subtype} policy for category "${data.category_name}" and role "${data.role}"`,
                hide: false,
                opacity: 0.9,
                confirm: { confirm: true },
                buttons: { closer: false, sticker: false },
                history: { history: false },
                addclass: 'pnotify-center'
            }).get().on('pnotify.confirm', function () {
                $.ajax({
                    type: 'DELETE',
                    url: `/api/v3/admin/authentication/policy/${data.subtype}/${data.id}`,
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
                        if (data.subtype == "password") {
                            password_policy_table.ajax.reload();
                        } else if (data.subtype == "email") {
                            email_policy_table.ajax.reload();
                        }
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR deleting ${data.subtype} policy`,
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
        } else if ($(this).attr('id') == 'btn-edit-policy') {
            var modal = '#modalPolicyEdit';
            $(modal + ` .policy_fields`).hide();
            $(modal + ` #${data.subtype}_fields`).show();
            $(modal + " #id").val(data.id);
            $(modal + " #subtype").val(data.subtype);
            $(modal + " #category").append(`<option value="${data.category}">${data.category_name}</option>`);
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
            $(modal + " #role").val(data.role);
            $.ajax({
                type: "GET",
                url: `/api/v3/admin/authentication/policy/${data.subtype}/${data.id}`,
                success: function (policy) {
                    if (policy.subtype == "password") {
                        $(modal + " #digits").val(policy.digits);
                        // $(modal + " #expire").val(policy.expire);
                        $(modal + " #length").val(policy["length"]);
                        $(modal + " #lowercase").val(policy.lowercase);
                        $(modal + " #not_username").val(String(policy.not_username));
                        $(modal + " #old_passwords").val(policy.old_passwords);
                        $(modal + " #special_characters").val(policy.special_characters);
                        $(modal + " #uppercase").val(policy.uppercase);
                    } else if (policy.subtype == "email") {
                        $(modal + " #days").val(policy.days);
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
        var subtype = $(modal + ' #subtype').val();
        if (subtype == "password") {
            var data = {
                'digits': parseInt(formData['digits']),
                'type': "local",
                // 'expire': parseInt(data['expire']),
                'length': parseInt(formData['length']),
                'lowercase': parseInt(formData['lowercase']),
                'old_passwords': parseInt(formData['old_passwords']),
                'uppercase': parseInt(formData['uppercase']),
                'special_characters': parseInt(formData['special_characters']),
                'not_username': formData['not_username'].toLowerCase() === 'true'
            };
        } else if (subtype == "email") {
            var data = {
                'days': parseInt(formData['days']),
            };
        }

        $.ajax({
            type: 'PUT',
            url: `/api/v3/admin/authentication/policy/${subtype}/${formData.id}`,
            data: JSON.stringify(data),
            contentType: "application/json",
            success: function (data) {
                $('form').each(function () { this.reset() });
                $('.modal').modal('hide');
                if (subtype == "password") {
                    password_policy_table.ajax.reload();
                } else if (subtype == "email") {
                    email_policy_table.ajax.reload();
                }
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
    });
});
