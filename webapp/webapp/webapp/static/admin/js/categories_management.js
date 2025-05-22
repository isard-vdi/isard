/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function () {
    $template_category = $(".template-detail-categories");
    $("#modalEditCategoryForm #span-custom-url").append(location.protocol + '//' + location.host + '/login/form/');
    $("#modalAddCategoryForm #span-custom-url").append(location.protocol + '//' + location.host + '/login/form/');

    var categories_table = $('#categories').DataTable({
        "initComplete": function (settings, json) {
            waitDefined('socket', initCategorySockets)
            let searchCategoryId = getUrlParam('searchCategory');
            if (searchCategoryId) {
                this.api().column([1]).search("(^" + searchCategoryId + "$)", true, false).draw();
                window.location.hash = '#categories'
                $('#categories .xe-name input').val(searchCategoryId)
            }
        },
        "ajax": {
            "url": "/admin/users/management/categories",
            "dataSrc": "",
            "type": "GET",
            "data": function (d) { return JSON.stringify({}) }
        },
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "columns": [
            {
                "className": 'details-show',
                "orderable": false,
                "data": null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "name", className: "xe-name" },
            { "data": "description", className: "xe-description" },
            { "data": "frontend", className: "xe-frontend" },
            { 
                "data": "bastion_domain",
                className: "xe-bastion_domain", 
                "render": function (data, type, full, meta) {
                    switch (data) {
                        case null:
                            return `<i class="fa fa-circle" aria-hidden="true" style="color:green" title="Default domain."></i>`
                        case false:
                            return `<i class="fa fa-circle" aria-hidden="true" style="color:darkgray" title="Bastion access disabled."></i>`
                        default:
                            return `<i class="fa fa-circle" aria-hidden="true" style="color:green"></i> ${data}`
                    }
                }
            },
            { "data": "authentication", className: "xe-authentication" },
            { "data": "ephemeral_desktops", className: "xe-ephemeral_desktops" },
            {
                'data': 'maintenance',
                'render': function (maintenance, type, row) {
                    return `<i class="fa fa-circle" aria-hidden="true"  style="color: ${ maintenance ? 'red' : 'grey' }" title="${ maintenance ? 'Maintenance enabled' : 'Maintenance disabled' }"></i>`
                }
            },
            { "data": "id", "visible": false }
        ],
        "columnDefs": [
            {
                "targets": 1,
                "render": function (data, type, full, meta) {
                    return '<a href="/isard-admin/admin/users/QuotasLimits?searchCategory=' + full.name + '">' + full.name + '</a>'
                }
            },
            {
                "targets": 3,
                "render": function (data, type, full, meta) {
                    if ('frontend' in full && full.frontend) {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:green" title="' + full.frontend + '"></i>'
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
            },
            {
                "targets": 5,
                "render": function (data, type, full, meta) {
                    domains = ""
                    
                    console.warn(full)

                    if (full.authentication) {
                        if (
                            full.authentication.local &&
                            full.authentication.local.enabled !== false &&
                            full.authentication.local.allowed_domains
                        ) {
                            const domainsText = full.authentication.local.allowed_domains.length === 0 ? 'Only users without email will be able to login' : full.authentication.local.allowed_domains.join(', ')
                            domains += `Local: <span title="local">${domainsText}</span>`
                        }
                        if (
                            full.authentication.google &&
                            full.authentication.google.enabled !== false &&
                            full.authentication.google.allowed_domains
                        ) {
                            const domainsText = full.authentication.google.allowed_domains.length === 0 ? 'Only users without email will be able to login' : full.authentication.google.allowed_domains.join(', ')
                            domains += ` Google: <span title="google">${domainsText}</span>`
                        }
                        if (
                            full.authentication.saml &&
                            full.authentication.saml.enabled !== false &&
                            full.authentication.saml.allowed_domains
                        ) {
                            const domainsText = full.authentication.saml.allowed_domains.length === 0 ? 'Only users without email will be able to login' : full.authentication.saml.allowed_domains.join(', ')
                            domains += ` SAML: <span title="saml">${domainsText}</span>`
                        }
                        if (
                            full.authentication.ldap &&
                            full.authentication.ldap.enabled !== false &&
                            full.authentication.ldap.allowed_domains
                        ) {
                            const domainsText = full.authentication.ldap.allowed_domains.length === 0 ? 'Only users without email will be able to login' : full.authentication.ldap.allowed_domains.join(', ')
                            domains += ` LDAP: <span title="ldap">${domainsText}</span>`
                        }

                        return domains
                    }
                }
            },
            {
                "targets": 6,
                "render": function (data, type, full, meta) {
                    if (full.ephimeral) {
                        return (full.ephimeral.action + " desktops every " + full.ephimeral.minutes + " minutes")
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
            }
        ],
    });

    showExportButtons(categories_table, 'categories-buttons-row')
    adminShowIdCol(categories_table)

    // Setup - add a text input to each footer cell
    $('#categories tfoot tr:first th').each(function () {
        var title = $(this).text();
        if (['', 'Frontend dropdown show', 'Ephemeral desktops', 'Maintenance'].indexOf(title) == -1) {
            $(this).html('<input type="text" placeholder="Search ' + title + '" />');
        }
    });

    // Apply the search
    categories_table.columns().every(function () {
        var that = this;

        $('input', this.footer()).on('keyup change', function () {
            if (that.search() !== this.value) {
                that
                    .search(this.value)
                    .draw();
            }
        });
    });

    $('#categories').find('tbody').on('click', 'td.details-show', function () {
        var tr = $(this).closest('tr');
        var row = categories_table.row(tr);

        if (row.child.isShown()) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            if (categories_table.row('.shown').length) {
                $('.details-show', categories_table.row('.shown').node()).click();
            }
            row.child(renderCategoriesDetailPannel(row.data())).show();
            actionsCategoryDetail();
            tr.addClass('shown');
        }
    });

    function initCategorySockets() {
        socket.on('categories_data', function (data) {
            categories_table.ajax.reload()
        });

        socket.on('categories_delete', function (data) {
            categories_table.ajax.reload()
        });
    }

    $("#modalDeleteCategory #send").on('click', function (e) {
        id = $('#modalDeleteCategoryForm #id').val();

        var notice = new PNotify({
            text: 'Deleting category...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        $('form').each(function () { this.reset() });
        $('.modal').modal('hide');
        $.ajax({
            type: "DELETE",
            url: "/api/v3/admin/category/" + id,
            contentType: "application/json",
            error: function (data) {
                notice.update({
                    title: 'ERROR deleting category',
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            },
            success: function (data) {
                notice.update({
                    title: 'Deleted',
                    text: 'Category deleted successfully',
                    hide: true,
                    delay: 2000,
                    icon: '',
                    opacity: 1,
                    type: 'success'
                })
            }
        });
    });

    $("#modalAuthentication #send").on('click', function (e) {
        var form = $('#modalAuthenticationForm');
        form.parsley().validate();
        if (form.parsley().isValid()) {
            var formData = form.serializeObject();
            var data = {};
            data.authentication = {}
            if ('local-enabled' in formData) {
                data["authentication"]["local"] = {
                    "enabled": formData['local-enabled'] === 'true' ? true : formData['local-enabled'] === 'false' ? false : null,
                    "allowed_domains": formData['local-domains'] || []
                };
            }
            if ('google-enabled' in formData) {
                data["authentication"]["google"] = {
                    "enabled": formData['google-enabled'] === 'true' ? true : formData['google-enabled'] === 'false' ? false : null,
                    "allowed_domains": formData['google-domains'] || []
                };
            }
            if ('saml-enabled' in formData) {
                data["authentication"]["saml"] = {
                    "enabled": formData['saml-enabled'] === 'true' ? true : formData['saml-enabled'] === 'false' ? false : null,
                    "allowed_domains": formData['saml-domains'] || []
                };
            }
            if ('ldap-enabled' in formData) {
                data["authentication"]["ldap"] = {
                    "enabled": formData['ldap-enabled'] === 'true' ? true : formData['ldap-enabled'] === 'false' ? false : null,
                    "allowed_domains": formData['ldap-domains'] || []
                };
            }
        };
        var notice = new PNotify({
            text: 'Updating allowed domains...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        });
        $.ajax({
            type: "PUT",
            url: "/api/v3/admin/category/" + formData['id'] + "/authentication",
            data: JSON.stringify(data),
            contentType: "application/json",
            success: function (response) {
                notice.update({
                    title: 'Updated',
                    text: 'Authentication updated successfully',
                    hide: true,
                    delay: 2000,
                    icon: '',
                    opacity: 1,
                    type: 'success'
                });
                $('form').each(function () { this.reset(); });
                $('.modal').modal('hide');
            },
            error: function (data) {
                notice.update({
                    title: 'ERROR updating authentication',
                    text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                });
            }
        });
        
    });

    $('.btn-new-category').on('click', function () {
        $('#modalAddCategory').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        removeError($('#modalAddCategory'));
        $('#modalAddCategoryForm')[0].reset();
        $('#modalAddCategoryForm :checkbox').iCheck('uncheck').iCheck('update');
        $('#modalAddCategoryForm #ephimeral-data').hide();
        // $('#modalAddCategoryForm #auto-desktops-data').hide();
        // autoDesktopsShow('#modalAddCategoryForm', {})
        maxTimeEnabledShow('#modalAddCategoryForm')
        storagePoolEnabledShow('#modalAddCategoryForm')
        $("#modalAddCategoryForm #max-recycle-bin-cutoff-time-data").hide();
        $("#modalAddCategoryForm #storage_pool").empty();
        $.ajax({
            type: "GET",
            url: "/api/v3/admin/storage_pools",
            contentType: "application/json",
            success: function (data) {
                $.each(data, function (index, value) {
                    const option = $('<option>', {
                        value: value.id,
                        text: value.name
                    });
                    if (!value.is_default) { $("#modalAddCategoryForm #storage_pool").append(option); }
                });
            }
        });
        $('#maxtime_panel :checkbox').iCheck('uncheck').iCheck('update');
        ephemeralDesktopsShow('#modalAddCategoryForm', {})

    });

    $('#modalAddCategory #send').on('click', function (e) {
        var form = $('#modalAddCategoryForm');
        form.parsley().validate();
        if (form.parsley().isValid()) {
            data = form.serializeObject();
            if (!data['uid']) {
                delete data['uid'];
            }
            data['frontend'] = 'frontend' in data;
            data['maintenance'] = 'maintenance' in data;
            if (!('ephimeral-enabled' in data)) {
                delete data['ephimeral-minutes'];
                delete data['ephimeral-action'];
            } else {
                delete data['ephimeral-enabled'];
                data['ephimeral-minutes'] = parseInt(data['ephimeral-minutes'])
            }
            if (!('storage-pool-enabled' in data)) {
                delete data['storage_pool'];
            } else {
                delete data['storage-pool-enabled'];
            }
            if ($('#modalAddCategoryForm #recycle-bin-cutoff-time-enabled').iCheck('update')[0].checked) {
                data['recycle_bin_cutoff_time'] = parseInt($('#modalAddCategoryForm #recycle-bin-cutoff-time').val());
            } else {
                data['recycle_bin_cutoff_time'] = null
            }
            // if (!('auto-desktops-enabled' in data)) {
            //     delete data['auto-desktops'];
            // }
            data = JSON.unflatten(data);
            var notice = new PNotify({
                text: 'Creating...',
                hide: false,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })
            $.ajax({
                type: "POST",
                url: "/api/v3/admin/category",
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function (data) {
                    $('form').each(function () { this.reset() });
                    $('.modal').modal('hide');
                    notice.update({
                        title: 'Created',
                        text: 'Category created successfully',
                        hide: true,
                        delay: 2000,
                        icon: '',
                        opacity: 1,
                        type: 'success'
                    })
                },
                error: function (data) {
                    notice.update({
                        title: 'ERROR creating category',
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                }
            });
        }
    });

    $('#modalBastionDomain #send').on('click', function (e) {
        var form = $('#modalBastionDomainForm');

        form.parsley().validate();
        if (form.parsley().isValid()) {
            var formData = form.serializeObject();
            var data = {}
            if (formData['bastion-enabled'] === 'true') {
                data['bastion_domain'] = formData['bastion-domain'];
            } else if (formData['bastion-enabled'] === "false") {
                data['bastion_domain'] = false;
            } else {
                data['bastion_domain'] = null;
            }

            var notice = new PNotify({
                text: 'Updating bastion domain...',
                hide: false,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })

            $.ajax({
                type: "PUT",
                url: `/api/v3/admin/category/${formData.id}/bastion_domain`,
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function (response) {
                    notice.update({
                        title: 'Updated',
                        text: 'Bastion domain updated successfully',
                        hide: true,
                        delay: 2000,
                        icon: '',
                        opacity: 1,
                        type: 'success'
                    });
                    $('form').each(function () { this.reset(); });
                    $('.modal').modal('hide');
                },
                error: function (data) {
                    notice.update({
                        title: 'ERROR updating bastion domain',
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                }
            })
        }
    });
});

function renderCategoriesDetailPannel(d) {
    if (d.editable == false) {
        $('.template-detail-categories .btn-delete').hide()
        $('.template-detail-categories .btn-edit-quotas').hide()
        $('.template-detail-categories .btn-edit-limits').hide()
    } else {
        $('.template-detail-categories .btn-delete').show()
        $('.template-detail-categories .btn-edit-quotas').show()
        $('.template-detail-categories .btn-edit-limits').show()
    }
    if (d.id == "default") { $('.template-detail-categories .btn-delete').hide() }
    $newPanel = $template_category.clone();
    $newPanel.html(function (i, oldHtml) {
        return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description);
    });
    return $newPanel
}


function actionsCategoryDetail() {
    $('.btn-edit-category').off('click').on('click', function () {
        var pk = $(this).closest("div").attr("data-pk");
        $("#modalEditCategoryForm")[0].reset();
        $("#modalEditCategoryForm #recycle-bin-cutoff-time-data").hide();
        $('#maxtime_panel #recycle-bin-cutoff-time-enabled').iCheck('uncheck').iCheck('update');
        $('#modalEditCategoryForm #id').val(pk);
        $('#modalEditCategory').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $.ajax({
            type: "GET",
            url: "/api/v3/admin/category/" + pk,
            contentType: "application/json",
            accept: "application/json"
        }).done(function (category) {
            $('#modalEditCategoryForm #name').val(category.name);
            $('#modalEditCategoryForm #custom-url').val(category.custom_url_name);
            $('#modalEditCategoryForm #uid').val(category.uid);
            $('#modalEditCategoryForm #description').val(category.description);
            $('#modalEditCategoryForm #id').val(category.id);
            $('#modalEditCategoryForm #allowed_domain').val(category.allowed_domain);

            if (category.recycle_bin_cutoff_time != null) {
                $("#modalEditCategoryForm #recycle-bin-cutoff-time-enabled").iCheck('check').iCheck('update');
                $('#modalEditCategoryForm #recycle-bin-cutoff-time').val(category.recycle_bin_cutoff_time);
                $("#modalEditCategoryForm #recycle-bin-cutoff-time-data").show();
            }

            if (category['frontend'] == true) {
                $('#modalEditCategoryForm #frontend').iCheck('check').iCheck('update');
            } else {
                $('#modalEditCategoryForm #frontend').iCheck('uncheck').iCheck('update');
            }
            if (category['maintenance'] == true) {
                $('#modalEditCategoryForm #maintenance').iCheck('check').iCheck('update');
            } else {
                $('#modalEditCategoryForm #maintenance').iCheck('uncheck').iCheck('update');
            }
            // autoDesktopsShow('#modalEditCategoryForm', category)
            maxTimeEnabledShow('#modalEditCategoryForm')
            ephemeralDesktopsShow('#modalEditCategoryForm', category)
        });

        $("#modalEditCategory #send").off('click').on('click', function (e) {
            var form = $('#modalEditCategoryForm');
            form.parsley().validate();
            if (form.parsley().isValid()) {
                data = form.serializeObject();
                data['id'] = $('#modalEditCategoryForm #id').val();
                data['name'] = $('#modalEditCategoryForm #name').val();
                data['frontend'] = 'frontend' in data;
                data['maintenance'] = 'maintenance' in data;
                if (!('ephimeral-enabled' in data)) {
                    delete data['ephimeral-minutes'];
                    delete data['ephimeral-action'];
                    data['ephimeral'] = false;
                } else {
                    delete data['ephimeral-enabled'];
                    data['ephimeral-minutes'] = parseInt(data['ephimeral-minutes'])
                }
                delete data["authentication_local"];
                delete data["authentication_google"];
                delete data["authentication_saml"];
                delete data["authentication_ldap"];

                if ($('#modalEditCategoryForm #recycle-bin-cutoff-time-enabled').iCheck('update')[0].checked) {
                    data['recycle_bin_cutoff_time'] = parseInt($('#modalEditCategoryForm #recycle-bin-cutoff-time').val())
                } else {
                    data['recycle_bin_cutoff_time'] = null
                }
                // if (!('auto-desktops-enabled' in data)) {
                //     delete data['auto-desktops'];
                //     data['auto'] = false;
                // }
                data = JSON.unflatten(data);
                var notice = new PNotify({
                    text: 'Updating category...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: "PUT",
                    url: "/api/v3/admin/category/" + data['id'],
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function (response) {
                        notice.update({
                            title: 'Updated',
                            text: 'Category updated successfully',
                            hide: true,
                            delay: 2000,
                            icon: '',
                            opacity: 1,
                            type: 'success'
                        })
                        $('.modal').modal('hide');
                    },
                    error: function (data) {
                        notice.update({
                            title: 'ERROR updating category',
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 2000,
                            opacity: 1
                        })
                    }
                });

            }
        });
    });

    $('#categories .btn-delete').off('click').on('click', function () {
        var pk = $(this).closest("div").attr("data-pk");
        var data = {
            'id': pk
        }
        $("#modalDeleteCategoryForm")[0].reset();
        $('#modalDeleteCategoryForm #id').val(pk);
        $('#modalDeleteCategory').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        showLoadingData('#modalDeleteCategory #table_modal_delete_desktops')
        showLoadingData('#modalDeleteCategory #table_modal_delete_templates')
        showLoadingData('#modalDeleteCategory #table_modal_delete_deployments')
        showLoadingData('#modalDeleteCategory #table_modal_delete_media')
        showLoadingData('#modalDeleteCategory #table_modal_delete_users')
        showLoadingData('#modalDeleteCategory #table_modal_delete_groups')
        $.ajax({
            type: "POST",
            url: "/api/v3/admin/category/delete/check",
            data: JSON.stringify({
                "ids": [pk]
            }),
            contentType: "application/json"
        }).done(function (items) {
            populateDeleteModalTable(items.desktops, $('#modalDeleteCategory #table_modal_delete_desktops'));
            populateDeleteModalTable(items.templates, $('#modalDeleteCategory #table_modal_delete_templates'));
            populateDeleteModalTable(items.deployments, $('#modalDeleteCategory #table_modal_delete_deployments'));
            populateDeleteModalTable(items.media, $('#modalDeleteCategory #table_modal_delete_media'));
            populateDeleteModalTable(items.users, $('#modalDeleteCategory #table_modal_delete_users'));
            populateDeleteModalTable(items.groups, $('#modalDeleteCategory #table_modal_delete_groups'));
            (items.storage_pools > 0) ? $("#modalDeleteCategory #storage-pool-warning").show() :  $("#modalDeleteCategory #storage-pool-warning").hide();
        });
    });

    $("#categories .btn-authentication").off("click").on("click", function () {
        var pk = $(this).closest("div").attr("data-pk");
        var modal = "#modalAuthentication";
        $.ajax({
          type: "GET",
          url: "/api/v3/admin/authentication/providers",
          contentType: "application/json",
          success: function (providers) {
            $.each(providers, function (key, value) {
              if (value) {
                $(modal + " #" + key + "-panel").show();
                $(modal + " #" + key + "-panel select").attr('disabled', false);
              } else {
                $(modal + " #" + key + "-panel").hide();
                $(modal + " #" + key + "-panel select").attr('disabled', true);
              }
            });
          },
        });
        $.ajax({
          type: "GET",
          url: "/api/v3/admin/category/" + pk,
          contentType: "application/json",
          success: function (category) {
            if (category.is_default) {
                $(modal + " #default-category-alert").show();
            } else {
                $(modal + " #default-category-alert").hide();
            }
            $.each(category.authentication, function (key, value) {
            var enabledValue = value.enabled === null ? "null" : value.enabled.toString();
              $(modal + " #" + key + "-enabled").val(enabledValue).trigger('change');
              $(modal + ` .authentication-panel #${key}-domains`).empty();
              $.each(value.allowed_domains, function (_, domain) {
                var newOption = new Option(domain, domain, true, true);
                $(modal + ` .authentication-panel #${key}-domains`).append(newOption);
              });
            });
          },
        });
        $(modal + " .enabled-select").off("change").on("change", function () {
            if ($(this).val() === "true" || $(this).val() === null) {
              $(this).parents().eq(3).find(".authentication-panel").show();
              $(this).parents().eq(3).find(".authentication-panel select").attr('disabled', false);
            } else {
              $(this).parents().eq(3).find(".authentication-panel").hide();
              $(this).parents().eq(3).find(".authentication-panel select").attr('disabled', true);
            }
          }).trigger("change");
        $(modal + "  .authentication-panel select").select2({
          tags: true,
          tokenSeparators: [",", " "],
          placeholder: "Type one or multiple domains. Empty means any domain",
          width: "100%",
        });
        $(modal + " #id").val(pk);
        $(modal).modal({
            backdrop: "static",
            keyboard: false,
          }).modal("show");
      });


    $("#categories .btn-bastion-domain").off("click").on("click", function () {
        var pk = $(this).closest("div").attr("data-pk");
        var modal = "#modalBastionDomain";
        var domainVerified = true;
        $.ajax({
            type: "GET",
            url: "/api/v3/admin/category/" + pk + "/bastion_domain",
            contentType: "application/json",
            success: function (category) {
                switch (category.bastion_domain) {
                    case null:
                    $(modal + " #bastion-enabled").val("null").trigger('change');
                    $(modal + " #bastion-domain").val("");
                    break;
                    case false:
                    $(modal + " #bastion-enabled").val("false").trigger('change');
                    $(modal + " #bastion-domain").val("");
                    break;
                    default:
                    $(modal + " #bastion-enabled").val("true").trigger('change');
                    $(modal + " #bastion-domain").val(category.bastion_domain);
                    break;
                }
            },
        });
        $(modal + " #bastion-enabled").off("change").on("change", function () {
            if ($(this).val() === "true" || $(this).val() === null) {
                $(`${modal} #bastion-domain-panel`).show();
                $(`${modal} #wildcard-domain-alert`).show();
            } else {
                $(`${modal} #bastion-domain-panel`).hide();
                $(`${modal} #wildcard-domain-alert`).hide();
            }
        }).trigger("change");

        $(modal + " #id").val(pk);
        $(modal).modal({
            backdrop: "static",
            keyboard: false,
        }).modal("show");
    });
}

function customURLChange(titlestr) {
    var url = titlestr.replace(/ /g, "_");
    document.getElementsByName("custom_url_name")[0].value = url;
}

function ephemeralDesktopsShow(form, item) {
    // add group / category
    if (!('id' in item)) {
        $(form + " #ephimeral-minutes").ionRangeSlider({
            type: "single",
            min: 5,
            max: 120,
            step: 5,
            grid: true,
            disable: false
        }).data("ionRangeSlider").update();
    }

    // edit group / category with ephemeral
    else if (item.ephimeral) {
        $(form + (' #ephimeral-enabled')).iCheck('check').iCheck('update');
        if ($(form + ' #ephimeral-minutes').data("ionRangeSlider")) {
            $(form + (' #ephimeral-minutes')).data("ionRangeSlider").update({ from: item['ephimeral']['minutes'] });
        } else {
            $(form + (' #ephimeral-minutes')).ionRangeSlider({
                type: "single",
                from: item['ephimeral']['minutes'],
                min: 5,
                max: 120,
                step: 5,
                grid: true,
                disable: false
            }).data("ionRangeSlider").update();
        }
        $(form + (' #ephimeral-action option[value="' + item['ephimeral']['action'] + '"]')).prop("selected", true);
        $(form + (" #ephimeral-data")).show();

    // edit group / category without ephemeral
    } else {
        $(form + (' #ephimeral-enabled')).iCheck('uncheck').iCheck('update');
        $(form + (' #ephimeral-minutes')).ionRangeSlider({
            type: "single",
            min: 5,
            max: 120,
            step: 5,
            grid: true,
            disable: false
        }).data("ionRangeSlider").update();
        $(form + (" #ephimeral-data")).hide();
    }

    $(form + (" #ephimeral-enabled")).on('ifChecked', function(event){
        $(form + (" #ephimeral-data")).show();
    });
    $(form + (" #ephimeral-enabled")).on('ifUnchecked', function(event){
        $(form + (" #ephimeral-data")).hide();
    });
}

// function autoDesktopsShow(form, item) {
//     if (item.auto) {
//         $(form + (" #auto-desktops-enabled")).iCheck('check').iCheck('update');
//         $(form + (" #auto-desktops")).empty()

//         item['auto']['desktops'].forEach(function (dom_id) {
//             api.ajax('/api/v3/admin/table/domains', 'POST', { 'id': dom_id, 'pluck': ['id', 'name'] }).done(function (dom) {
//                 var newOption = new Option(dom.name, dom.id, true, true);
//                 $(form + (" #auto-desktops")).append(newOption).trigger('change');
//             });
//         });
//         $(form + (" #auto-desktops-data")).show();
//     } else {
//         $(form + (" #auto-desktops-enabled")).iCheck('unckeck').iCheck('update');
//         $(form + (" #auto-desktops-data")).hide();
//     }

//         $(form + (" #auto-desktops")).select2({
//         minimumInputLength: 2,
//         multiple: true,
//         ajax: {
//             type: "GET",
//             url: '/api/v3/user/templates/allowed/all',
//             dataType: 'json',
//             contentType: "application/json",
//             delay: 250,
//             data: function (params) {
//                 return  JSON.stringify({
//                     term: params.term,
//                     pluck: ['id','name']
//                 });
//             },
//             processResults: function (data) {
//                 return {
//                     results: $.map(data, function (item, i) {
//                         return {
//                             text: item.name,
//                             id: item.id
//                         }
//                     })
//                 };
//             }
//         },
//     });

//     $(form + (" #auto-desktops-enabled")).on('ifChecked', function(event){
//         $(form + (" #auto-desktops-data")).show();
//     });
//     $(form + (" #auto-desktops-enabled")).on('ifUnchecked', function(event){
//         $(form + (" #auto-desktops-data")).hide();
//     });
// }

function maxTimeEnabledShow (form) {
    $(form + (" #recycle-bin-cutoff-time-enabled")).on('ifChecked', function(event){
        $(form + (" #recycle-bin-cutoff-time-data")).show();
    });
    $(form + (" #recycle-bin-cutoff-time-enabled")).on('ifUnchecked', function(event){
        $(form + (" #recycle-bin-cutoff-time-data")).hide();
    });
}

function storagePoolEnabledShow(form) {
  $(form + " #storage-pool-data").hide();
  $(form + " #storage-pool-enabled").on("ifChecked", function (event) {
    $(form + " #storage-pool-data").show();
  });
  $(form + " #storage-pool-enabled").on("ifUnchecked", function (event) {
    $(form + " #storage-pool-data").hide();
  });
}
