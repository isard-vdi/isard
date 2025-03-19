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
            { "data": "allowed_domains", className: "xe-allowed_domains" },
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
                "targets": 4,
                "render": function (data, type, full, meta) {
                    domains = ""

                    if (full.allowed_domains) {
                        if (full.allowed_domains.local && full.allowed_domains.local.length > 0) {
                            domains += '<span title="local">' + full.allowed_domains.local.join(', ') + '</span>'
                        }
                        if (full.allowed_domains.google && full.allowed_domains.google.length > 0) {
                            if (domains.length > 0) {
                                domains += ' │ '
                            }
                            domains += '<span title="google">' + full.allowed_domains.google.join(', ') + '</span>'
                        }
                        if (full.allowed_domains.saml && full.allowed_domains.saml.length > 0) {
                            if (domains.length > 0) {
                                domains += ' │ '
                            }
                            domains += '<span title="saml">' + full.allowed_domains.saml.join(', ') + '</span>'
                        }
                        if (full.allowed_domains.ldap && full.allowed_domains.ldap.length > 0) {
                            if (domains.length > 0) {
                                domains += ' │ '
                            }
                            domains += '<span title="ldap">' + full.allowed_domains.ldap.join(', ') + '</span>'
                        }

                        return domains
                    }
                }
            },
            {
                "targets": 5,
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
        $("#modalAddCategoryForm #max-delete-data").hide();
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
        api.ajax('/scheduler/recycle_bin_delete/max_time', 'GET', '').done(function (time) {
            if (time.time !== "null") {
                var maxTime = parseInt(time.time);
                $('#modalAddCategoryForm #max-delete option').each(function () {
                    if (($(this).val() > maxTime || $(this).val() == "null")) {
                        $(this).remove();
                    }
                });
            };
        });
        ephemeralDesktopsShow('#modalAddCategoryForm', {})

    });

    $("#modalAddCategory #send").on('click', function (e) {
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
            // if (!('auto-desktops-enabled' in data)) {
            //     delete data['auto-desktops'];
            // }
            data["allowed_domains"] = {
                "local": splitAllowedDomains(data["allowed_domains_local"]),
                "google": splitAllowedDomains(data["allowed_domains_google"]),
                "saml": splitAllowedDomains(data["allowed_domains_saml"]),
                "ldap": splitAllowedDomains(data["allowed_domains_ldap"])
            }
            data = JSON.unflatten(data);
            max_time = false;
            if (data['max']['time'] == 'on') {
                max_time = data['max']['delete'];
            };
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
                    if (max_time){
                        $.ajax({
                            type: "PUT",
                            url: "/scheduler/recycle_bin/" + max_time + "/" + data['id'],
                            contentType: "application/json",
                        });
                    }
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
        $("#modalEditCategoryForm #max-delete-data").hide();
        $('#maxtime_panel #max-time-enabled').iCheck('uncheck').iCheck('update');
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

            api.ajax('/api/v3/admin/authentication/providers', 'GET', '').done(function (providers) {
                if (providers.local === true) {
                    $('#modalEditCategoryForm #allowed_domains_local_container').attr('hidden', false);
                    $('#modalEditCategoryForm #allowed_domains_local').val(category.allowed_domains.local);
                }
                if (providers.google === true) {
                    $('#modalEditCategoryForm #allowed_domains_google_container').attr('hidden', false);
                    $('#modalEditCategoryForm #allowed_domains_google').val(category.allowed_domains.google);
                }
                if (providers.saml === true) {
                    $('#modalEditCategoryForm #allowed_domains_saml_container').attr('hidden', false);
                    $('#modalEditCategoryForm #allowed_domains_saml').val(category.allowed_domains.saml);
                }
                if (providers.ldap === true) {
                    $('#modalEditCategoryForm #allowed_domains_ldap_container').attr('hidden', false);
                    $('#modalEditCategoryForm #allowed_domains_ldap').val(category.allowed_domains.ldap);
                }
            });
            api.ajax('/scheduler/recycle_bin_delete/max_time_category/' + category.id, 'GET', '').done(function (time) {
                if (time != null) {
                    $(("#modalEditCategoryForm #max-time-enabled")).iCheck('check').iCheck('update');
                    $('#modalEditCategoryForm #max-delete').val(time)
                } else {
                    $(("#modalEditCategoryForm #max-time-enabled")).iCheck('uncheck').iCheck('update');
                }
            });
            api.ajax('/scheduler/recycle_bin_delete/max_time', 'GET', '').done(function (time) {
                if (time.time !== "null") {
                    var maxTime = parseInt(time.time);
                    $('#modalEditCategoryForm #max-delete option').each(function () {
                        if (($(this).val() > maxTime || $(this).val() === "null")) {
                            $("#modalAddCategoryForm #max-delete-data").show();
                            $(this).remove();
                        }
                    });
                };
            });
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
                // if (!('auto-desktops-enabled' in data)) {
                //     delete data['auto-desktops'];
                //     data['auto'] = false;
                // }
                data["allowed_domains"] = {
                    "local": splitAllowedDomains(data["allowed_domains_local"]),
                    "google": splitAllowedDomains(data["allowed_domains_google"]),
                    "saml": splitAllowedDomains(data["allowed_domains_saml"]),
                    "ldap": splitAllowedDomains(data["allowed_domains_ldap"])
                }
                delete data["allowed_domains_local"];
                delete data["allowed_domains_google"];
                delete data["allowed_domains_saml"];
                delete data["allowed_domains_ldap"];
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
                        if (data['max']['time'] == 'on') {
                            max_time = data['max']['delete'];
                            $.ajax({
                                type: "PUT",
                                url: "/scheduler/recycle_bin/" + max_time + "/" + data['id'],
                                contentType: "application/json",
                                success: function (data) {
                                    notice.update({
                                        title: 'Updated',
                                        text: 'Category updated successfully',
                                        hide: true,
                                        delay: 1000,
                                        icon: 'fa fa-' + data.icon,
                                        opacity: 1,
                                        type: 'success'
                                    })
                                    $('form').each(function () { this.reset() });
                                    $('.modal').modal('hide');
                                },
                                error: function (data) {
                                    new PNotify({
                                        title: 'ERROR changing automatic delete time',
                                        text: response.responseJSON.description,
                                        type: 'error',
                                        hide: true,
                                        icon: 'fa fa-warning',
                                        delay: 2000,
                                        opacity: 1
                                    })
                                }
                            });
                        } else {
                            $.ajax({
                                type: "DELETE",
                                url: "/scheduler/delete/recycle_bin/" + data['id'],
                                contentType: "application/json",
                                success: function (data) {
                                    notice.update({
                                        title: 'Updated',
                                        text: 'Category updated successfully',
                                        hide: true,
                                        delay: 1000,
                                        icon: '',
                                        opacity: 1,
                                        type: 'success'
                                    })
                                    $('form').each(function () { this.reset() });
                                    $('.modal').modal('hide');
                                }
                            })
                        }
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
    $(form + (" #max-time-enabled")).on('ifChecked', function(event){
        $(form + (" #max-delete-data")).show();
    });
    $(form + (" #max-time-enabled")).on('ifUnchecked', function(event){
        $(form + (" #max-delete-data")).hide();
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

function splitAllowedDomains(data) {
    return data.split(',').map(function (item) { return item.trim() }).filter(function (item) { return item.length > 0 });
}
