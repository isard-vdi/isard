/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {
    $template_group = $(".template-detail-groups");
    var groups_table=$('#groups').DataTable( {
        "initComplete": function(settings, json) {
            waitDefined('socket', initGroupSockets)
            let searchGroupId = getUrlParam('searchGroup');
            if (searchGroupId) {
                this.api().column([1]).search("(^" + searchGroupId + "$)", true, false).draw();
                window.location.hash = '#groups'
                $('#groups .xe-name input').val(searchGroupId)
            }
        },
        "ajax": {
            "url": "/admin/users/management/groups",
            "dataSrc": "",
            "type" : "GET",
            "data": function(d){return JSON.stringify({})}
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
                "defaultContent": '<button class="btn btn-xs btn-info" type="button" data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "name", className: "xe-name" },
            { "data": "parent_category_name", className: "xe-category" },
            { "data": "description", className: "xe-description" },
            { "data": "linked_groups", className: "xe-linked_groups" },
            { "data": "ephemeral_desktops", className: "xe-ephemeral_desktops" },
            { "data": "id", "visible": false}
        ],
        "columnDefs": [
            {
                "targets": 1,
                "render": function ( data, type, full, meta ) {
                    return '<a href="/isard-admin/admin/users/QuotasLimits?searchGroup='+ full.name +'">'+ full.name +'</a>'
                }
            },
            {
                "targets": 2,
                "render": function ( data, type, full, meta ) {
                    return full.parent_category_name ? full.parent_category_name : ''
                }
            },
            {
                "targets": 4,
                "render": function ( data, type, full, meta ) {
                    return full.linked_groups_names
                }
            },
            {
                "targets": 5,
                "render": function ( data, type, full, meta ) {
                    if (full.ephimeral) {
                        return (full.ephimeral.action + " desktops every " + full.ephimeral.minutes + " minutes")
                    } else {
                        return false
                    }
                }
            }
        ]
    } );

    showExportButtons(groups_table, 'groups-buttons-row')
    adminShowIdCol(groups_table)

    // Hide 'Category' group list column when manager
    if ($('meta[id=user_data]').attr('data-role') == 'manager') {
        var column = groups_table.column(2);
        column.visible(!column.visible());
    }

    // Setup - add a text input to each footer cell
    $('#groups tfoot tr:first th').each( function () {
        var title = $(this).text();
        if (['', 'Ephemeral desktops'].indexOf(title) == -1){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );

    // Apply the search
    groups_table.columns().every( function () {
        var that = this;

        $( 'input', this.footer() ).on( 'keyup change', function () {
            if ( that.search() !== this.value ) {
                that
                .search( this.value )
                .draw();
            }
        } );
    } );

    $('#groups').find('tbody').on('click', 'td.details-show', function () {
        var tr = $(this).closest('tr');
        var row = groups_table.row( tr );

        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            if ( groups_table.row( '.shown' ).length ) {
                $('.details-show', groups_table.row( '.shown' ).node()).click();
            }
            row.child( renderGroupsDetailPannel(row.data()) ).show();
            actionsGroupDetail()
            tr.addClass('shown');
        }
    });


    function initGroupSockets() {
        socket.on('groups_data', function (data) {
            groups_table.ajax.reload()
        });

        socket.on('groups_delete', function (data) {
            groups_table.ajax.reload()
        });
    }

    $("#modalDeleteGroup #send").on('click', function(e){
        id=$('#modalDeleteGroupForm #id').val();

        var notice = new PNotify({
            text: 'Deleting group...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        $('form').each(function() { this.reset() });
        $('.modal').modal('hide');
        $.ajax({
            type: "DELETE",
            url:"/api/v3/admin/group/"+id ,
            contentType: "application/json",
            error: function(data) {
                notice.update({
                    title: 'ERROR deleting group',
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            },
            success: function(data)
            {
                notice.update({
                    title: 'Deleted',
                    text: 'Group deleted successfully',
                    hide: true,
                    delay: 2000,
                    icon: '',
                    opacity: 1,
                    type: 'success'
                })
            }
        });
        });

	$('.btn-new-group').on('click', function () {
        $('#modalAddGroup').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        removeError($('#modalAddGroup'))
        $('#modalAddGroupForm')[0].reset();
        $('#modalAddGroupForm :checkbox').iCheck('uncheck').iCheck('update');
        $('#modalAddGroupForm #ephimeral-data').hide();
        // $('#modalAddGroupForm #auto-desktops-data').hide();

        $('#modalAddGroupForm #linked_groups').select2({
            minimumInputLength: 2,
            multiple: true,
            ajax: {
                type: "POST",
                url: '/api/v3/admin/allowed/term/groups/',
                dataType: 'json',
                contentType: "application/json",
                delay: 250,
                data: function (params) {
                    return  JSON.stringify({
                        term: params.term,
                    });
                },
                processResults: function (data) {
                    return {
                        results: $.map(data, function (item, i) {
                            return {
                                text: item.name,
                                id: item.id
                            }
                        })
                    };
                }
            },
        });
        $.ajax({
            type: "GET",
            url:"/api/v3/admin/userschema",
            success: function (d) {
                $.each(d, function(key, value) {
                    if(key == 'category'){
                        $("#parent_category").find('option').remove().end();
                        for(var i in d[key]){
                            $("#parent_category").append('<option value=' + value[i].id + '>' + value[i].name + ' - ' + value[i].description + '</option>');
                        }
                    }
                });
            }
        });
        ephemeralDesktopsShow('#modalAddGroupForm', {})
        // autoDesktopsShow('#modalAddGroupForm', {})
	});

    $("#modalAddGroup #send").on('click', function(e){
            var form = $('#modalAddGroupForm');
            form.parsley().validate();
            if (form.parsley().isValid()){
                data=$('#modalAddGroupForm').serializeObject();
                data = form.serializeObject();
                if(!data['ephimeral-enabled']){
                    delete data['ephimeral-minutes'];
                    delete data['ephimeral-action'];
                }else{
                    delete data['ephimeral-enabled'];
                    data['ephimeral-minutes'] = parseInt(data['ephimeral-minutes'])
                }
                delete data['ephimeral-enabled'];
                // delete data['auto-desktops-enabled'];
                data=JSON.unflatten(data);
                var notice = new PNotify({
                    text: 'Creating group...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/group",
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function(data)
                    {
                        $('form').each(function() { this.reset() });
                        $('.modal').modal('hide');
                        notice.update({
                            title: "Created",
                            text: 'Group created successfully',
                            hide: true,
                            delay: 2000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                    },
                    error: function (data) {
                        notice.update({
                            title: 'ERROR creating group',
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

function renderGroupsDetailPannel ( d ) {
    $newPanel = $template_group.clone();
    $newPanel.html(function(i, oldHtml){
        var linked_groups_names = []
            $.each(d.linked_groups_data, function(i, group) {
                linked_groups_names.push(group.name)
            })
        return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description).replace(/d.linked_groups/g, linked_groups_names);
    });
    return $newPanel
}

function actionsGroupDetail(){

    $('.btn-edit-group').off('click').on('click', function () {
        $('#modalEditGroup').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        var pk = $(this).closest("div").attr("data-pk");
        $("#modalEditGroupForm")[0].reset();
        $("#modalEditGroupForm #linked_groups").empty().trigger('change')

        $('#modalEditGroupForm #linked_groups').select2({
            minimumInputLength: 2,
            multiple: true,
            ajax: {
                type: "POST",
                url: '/api/v3/admin/allowed/term/groups/',
                dataType: 'json',
                contentType: "application/json",
                delay: 250,
                data: function (params) {
                    return  JSON.stringify({
                        term: params.term,
                    });
                },
                processResults: function (data) {
                    return {
                        results: $.map(data, function (item, i) {
                            return {
                                text: item.name,
                                id: item.id
                            }
                        })
                    };
                }
            },
        });

        $.ajax({
            type: "GET",
            url: "/api/v3/admin/group/" + pk,
            contentType: "application/json",
            success: function (group) {
                $('#modalEditGroupForm #id').val(pk);
                $('#modalEditGroupForm #name').val(group.name);
                $('#modalEditGroupForm #description').val(group.description);
                $.each(group.linked_groups_data, function(i, group) {
                    var newOption = new Option(group.name, group.id, true, true);
                    $('#modalEditGroupForm #linked_groups').append(newOption).trigger('change');
                });
                $('#modalEditGroupForm :checkbox').iCheck('uncheck').iCheck('update');

                // autoDesktopsShow('#modalEditGroupForm', group)
                ephemeralDesktopsShow('#modalEditGroupForm', group)          

                $.each(group.linked_groups_data, function(i, group) {
                    var newOption = new Option(group.name, group.id, true, true);
                    $("#modalEditGroupForm #linked_groups").append(newOption).trigger('change');
                })
            }
        });


        $("#modalEditGroup #send").off('click').on('click', function (e) {
            var form = $('#modalEditGroupForm');
            form.parsley().validate();
            if (form.parsley().isValid()) {
                data = form.serializeObject();
                if(!data['ephimeral-enabled']){
                    delete data['ephimeral-minutes'];
                    delete data['ephimeral-action'];
                    data['ephimeral'] = false
                }else{
                    delete data['ephimeral-enabled'];
                    data['ephimeral-minutes'] = parseInt(data['ephimeral-minutes'])
                }
                if (!data["linked_groups"]) {
                    data["linked_groups"] = [];
                }
                // if (!('auto-desktops-enabled' in data)) {
                //     delete data['auto-desktops'];
                //     data['auto'] = false
                // }
                data = JSON.unflatten(data);
                var notice = new PNotify({
                    text: 'Updating group...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: "PUT",
                    url: "/api/v3/admin/group/" + data['id'],
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function (data) {
                        notice.update({
                            title: 'Updated',
                            text: 'Group updated successfully',
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
                        notice.update({
                            title: 'ERROR updating group',
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

    $('#groups .btn-delete').off('click').on('click', function () {
        var pk=$(this).closest("div").attr("data-pk");

        $("#modalDeleteGroupForm")[0].reset();
        $('#modalDeleteGroupForm #id').val(pk);
        $('#modalDeleteGroup').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        // setModalUser()
        // setQuotaTableDefaults('#edit-users-quota','users',pk)
        showLoadingData('#modalDeleteGroup #table_modal_delete_desktops')
        showLoadingData('#modalDeleteGroup #table_modal_delete_templates')
        showLoadingData('#modalDeleteGroup #table_modal_delete_deployments')
        showLoadingData('#modalDeleteGroup #table_modal_delete_media')
        showLoadingData('#modalDeleteGroup #table_modal_delete_users')
        showLoadingData('#modalDeleteGroup #table_modal_delete_groups')
        $.ajax({
            type: "POST",
            url: "/api/v3/admin/group/delete/check",
            data: JSON.stringify({
                "ids": [pk]
            }),
            contentType: "application/json"
        }).done(function (items) {
            populateDeleteModalTable(items.desktops, $('#modalDeleteGroup #table_modal_delete_desktops'));
            populateDeleteModalTable(items.templates, $('#modalDeleteGroup #table_modal_delete_templates'));
            populateDeleteModalTable(items.deployments, $('#modalDeleteGroup #table_modal_delete_deployments'));
            populateDeleteModalTable(items.media, $('#modalDeleteGroup #table_modal_delete_media'));
            populateDeleteModalTable(items.users, $('#modalDeleteGroup #table_modal_delete_users'));
            populateDeleteModalTable(items.groups, $('#modalDeleteGroup #table_modal_delete_groups'));
        });
    });

    $('.btn-enrollment').on('click', function () {
        var pk=$(this).closest("div").attr("data-pk");
        $("#modalEnrollmentForm")[0].reset();
        $('#modalEnrollmentForm #id').val(pk);
        $('#modalEnrollment').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $.ajax({
            type: 'GET',
            url: '/api/v3/admin/group/' + pk,
        }).done(function(data) {
            if(data.enrollment.manager != false){
                $('#manager-key').show();
                $('.btn-copy-manager').show();
                $('#manager-key').val('test');
                $('#manager-check').iCheck('check');
                $('#manager-key').val(data.enrollment.manager);
            }else{
                // https://github.com/dargullin/icheck/issues/159
                $('#manager-check').iCheck('uncheck').iCheck('update');
                $('#manager-key').hide();
                $('.btn-copy-manager').hide();
            }
            if(data.enrollment.advanced != false){
                $('#advanced-key').show();
                $('.btn-copy-advanced').show();
                $('#advanced-key').val('test');
                $('#advanced-check').iCheck('check');
                $('#advanced-key').val(data.enrollment.advanced);
            }else{
                // https://github.com/dargullin/icheck/issues/159
                $('#advanced-check').iCheck('uncheck').iCheck('update');
                $('#advanced-key').hide();
                $('.btn-copy-advanced').hide();
            }
            if(data.enrollment.user != false){
                $('#user-key').show();
                $('.btn-copy-user').show();
                $('#user-key').val('test');
                $('#user-check').iCheck('check');
                $('#user-key').val(data.enrollment.user);
            }else{
                // https://github.com/dargullin/icheck/issues/159
                $('#user-check').iCheck('uncheck').iCheck('update');
                $('#user-key').hide();
                $('.btn-copy-user').hide();
            }
        });
    });

    $('#groups .btn-migrate').off('click').on('click', function () {
        var pk = $(this).closest("div").attr("data-pk");
        $('#modalMigrateUsersGroup').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $("#modalMigrateUsersGroupForm")[0].reset();
        $('#modalMigrateUsersGroupForm #id').val(pk);
        $('#modalMigrateUsersGroupForm #category').prop('disabled', true)


        var current_category = null
        $.ajax({
            type: "GET",
            url: "/api/v3/admin/userschema",
            async: false,
            success: function (d) {
                $.each(d, function (key, value) {
                    $("#modalMigrateUsersGroup ." + key).find('option').remove().end();
                    $("#modalMigrateUsersGroup .group").append('<option value="null" disabled selected>--Please select a group--</option>');
                    for (var i in d[key]) {
                        if (key == 'group') {
                            $("#modalMigrateUsersGroup ." + key).append('<option value=' + value[i].id + ' parent-category=' + value[i].parent_category + '>' + value[i].name + '</option>');
                        } else {
                            $("#modalMigrateUsersGroup ." + key).append('<option value=' + value[i].id + '>' + value[i].name + '</option>');
                        }
                    }
                });
                current_category = d['group'].find(x => x.id == pk).parent_category
                $('#modalMigrateUsersGroup #category').val(current_category).trigger("change")
                filter_groups($("#modalMigrateUsersGroup #category"), $('#modalMigrateUsersGroup #group'), pk)
                $('#modalMigrateUsersGroup #group').val("null").trigger("change")

                if (d['group'].find(x => x.id == pk).external_gid !== null) {
                    $('#modalMigrateUsersGroup #external_user_group_warn').show()
                } else {
                    $('#modalMigrateUsersGroup #external_user_group_warn').hide()
                }
            }
        });

        function filter_groups(category_select, group_select, current_group=null) {
            // Hide all options
            group_select.find('option').attr("hidden", "hidden")
            // Show groups from the selected category
            group_select.find('option[parent-category=' + category_select.val() + ']').removeAttr('hidden')
            // If current_group is provided, hide it from the dropdown
            if (current_group) {
                group_select.find('option[value=' + current_group + ']').attr("hidden", "hidden")
            }
        }

        $("#modalMigrateUsersGroup #category").on('change', function () {
            filter_groups($(this), $('#modalMigrateUsersGroup #group'))
        })

        showLoadingData('#modalMigrateUsersGroup #table_modal_migrate_users_group')
        $.ajax({
            type: "POST",
            url: "/api/v3/admin/group/delete/check",
            data: JSON.stringify({
                "ids": [pk]
            }),
            contentType: "application/json"
        }).done(function (items) {
            populateDeleteModalTable(items.users, $('#modalMigrateUsersGroup #table_modal_migrate_users_group'));
        });


        $("#modalMigrateUsersGroup #send").off('click').on('click', function (e) {
            var form = $('#modalMigrateUsersGroupForm');
            form.parsley().validate();
            if (form.parsley().isValid()) {
                data = form.serializeObject();
                $.ajax({
                    type: "GET",
                    url: "/api/v3/admin/group/" + data['id'] + "/users/",
                    contentType: "application/json",
                    success: function (users) {
                        data = JSON.unflatten(data)
                        var notice = new PNotify({
                            text: 'Updating users...',
                            hide: false,
                            opacity: 1,
                            icon: 'fa fa-spinner fa-pulse'
                        })
                        $.ajax({
                            type: "PUT",
                            url: "/api/v3/admin/users/bulk/",
                            data: JSON.stringify({
                                ids: users,
                                category: data['category'],
                                group: data['group']
                            }),
                            contentType: "application/json",
                            success: function (data) {
                                notice.update({
                                    hide: true,
                                    delay: 1000,
                                })
                                $('form').each(function () { this.reset() });
                                $('.modal').modal('hide');
                            },
                            error: function (data) {
                                notice.update({
                                    title: 'Error updating users',
                                    text: data.responseJSON.description,
                                    type: 'error',
                                    hide: true,
                                    icon: 'fa fa-warning',
                                    delay: 2000,
                                    opacity: 1
                                })
                            }
                        });
                    },
                    error: function (data) {
                        notice.update({
                            title: 'Error getting users',
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

    $('#groups .btn-empty').off('click').on('click', function () {
        var pk = $(this).closest("div").attr("data-pk");

        $("#modalEmptyGroupForm")[0].reset();
        $('#modalEmptyGroupForm :checkbox').iCheck('uncheck').iCheck('update');
        $('#modalEmptyGroupForm').parsley().reset();

        $('#modalEmptyGroupForm #id').val(pk);
        $('#modalEmptyGroupForm #delete-action :radio').prop('required', true)
        $('#modalEmptyGroupForm #delete-action :radio').iCheck('uncheck').iCheck('update');
        $('#modalEmptyGroupForm #delete-action #delete-user').iCheck('check').iCheck('update');
        $('#modalEmptyGroup h4 #group-name').text($(this).closest("div").data("name"));

        $('#modalEmptyGroup').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');

        showLoadingData('#modalEmptyGroup #table_modal_delete_desktops')
        showLoadingData('#modalEmptyGroup #table_modal_delete_templates')
        showLoadingData('#modalEmptyGroup #table_modal_delete_deployments')
        showLoadingData('#modalEmptyGroup #table_modal_delete_media')
        showLoadingData('#modalEmptyGroup #table_modal_delete_users')
        showLoadingData('#modalEmptyGroup #table_modal_delete_groups')
        $.ajax({
            type: "POST",
            url: "/api/v3/admin/group/delete/check",
            data: JSON.stringify({
                "ids": [pk]
            }),
            contentType: "application/json"
        }).done(function (items) {
            populateDeleteModalTable(items.desktops, $('#modalEmptyGroup #table_modal_delete_desktops'));
            populateDeleteModalTable(items.templates, $('#modalEmptyGroup #table_modal_delete_templates'));
            populateDeleteModalTable(items.deployments, $('#modalEmptyGroup #table_modal_delete_deployments'));
            populateDeleteModalTable(items.media, $('#modalEmptyGroup #table_modal_delete_media'));
            populateDeleteModalTable(items.users, $('#modalEmptyGroup #table_modal_delete_users'));
            populateDeleteModalTable(items.groups, $('#modalEmptyGroup #table_modal_delete_groups'));
        });


        $("#modalEmptyGroup #send").off('click').on('click', function (e) {
            var form = $('#modalEmptyGroupForm');
            form.parsley().validate();
            if (form.parsley().isValid()) {
                data = form.serializeObject();
                $.ajax({
                    type: "GET",
                    url: "/api/v3/admin/group/" + pk + "/users/",
                    contentType: "application/json",
                    success: function (users) {
                        var notice = new PNotify({
                            text: 'Deleting users...',
                            hide: false,
                            opacity: 1,
                            icon: 'fa fa-spinner fa-pulse'
                        })
                        $.ajax({
                            type: "DELETE",
                            url: "/api/v3/admin/user",
                            data: JSON.stringify({
                                user: users,
                                delete_user: data['delete-user']
                            }),
                            contentType: "application/json",
                            success: function (data) {
                                notice.update({
                                    title: 'Deleted',
                                    text: 'Starting users deletion',
                                    hide: true,
                                    delay: 1000,
                                    icon: 'fa fa-sad',
                                    opacity: 1,
                                    type: 'success'
                                })
                                $('form').each(function () { this.reset() });
                                $('.modal').modal('hide');
                            },
                            error: function (data) {
                                notice.update({
                                    title: 'ERROR deleting users',
                                    text: data.responseJSON.description,
                                    type: 'error',
                                    hide: true,
                                    icon: 'fa fa-warning',
                                    delay: 2000,
                                    opacity: 1
                                })
                            }
                        });
                    },
                    error: function (data) {
                        notice.update({
                            title: 'ERROR getting users',
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

    $('#manager-check').unbind('ifChecked').on('ifChecked', function(event){
        if($('#manager-key').val()==''){
            const data = {}
            data['id']=$('#modalEnrollmentForm #id').val();
            data['role']="manager";
            data['action']="reset";
            $.ajax({
                type: "POST",
                data: JSON.stringify(data),
                url:"/api/v3/admin/group/enrollment",
                contentType: "application/json",
                success: function(data){
                    $('#manager-key').val(data);
                }
            });
            $('#manager-key').show();
            $('.btn-copy-manager').show();
        }
    });

    $('#manager-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
        const data = {}
        data['id']=$('#modalEnrollmentForm #id').val();
        data['role']="manager";
        data['action']="disable";
        new PNotify({
            title: 'Confirmation Needed',
            text: "Are you sure you want to delete manager code?",
            hide: false,
            opacity: 0.9,
            confirm: {
                confirm: true
            },
            buttons: {
                closer: false,
                sticker: false
            },
            history: {
                history: false
            },
            addclass: 'pnotify-center'
        }).get().on('pnotify.confirm', function() {
            pk=$('#modalEnrollmentForm #id').val();
            $.ajax({
                type: "POST",
                data: JSON.stringify(data),
                url:"/api/v3/admin/group/enrollment",
                contentType: "application/json",
                success: function(data){
                    $('#manager-key').val('');
                }
            })
            $('#manager-key').hide();
            $('.btn-copy-manager').hide();
        }).on('pnotify.cancel', function() {
            $('#manager-check').iCheck('check');
            $('#manager-key').show();
            $('.btn-copy-manager').show();
        });
    });

    $('#advanced-check').unbind('ifChecked').on('ifChecked', function(event){
        if($('#advanced-key').val()==''){
            const data = {}
            data['id']=$('#modalEnrollmentForm #id').val();
            data['role']="advanced";
            data['action']="reset";
            $.ajax({
                type: "POST",
                url:"/api/v3/admin/group/enrollment",
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function(data){
                    $('#advanced-key').val(data);
                }
            });
            $('#advanced-key').show();
            $('.btn-copy-advanced').show();
        }
    });
        
    $('#advanced-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
        const data = {}
        data['id']=$('#modalEnrollmentForm #id').val();
        data['role']="advanced";
        data['action']="disable";
        new PNotify({
            title: 'Confirmation Needed',
            text: "Are you sure you want to delete advanced code?",
            hide: false,
            opacity: 0.9,
            confirm: {
                confirm: true
            },
            buttons: {
                closer: false,
                sticker: false
            },
            history: {
                history: false
            },
            addclass: 'pnotify-center'
        }).get().on('pnotify.confirm', function() {
            pk=$('#modalEnrollmentForm #id').val();
            $.ajax({
                type: "POST",
                url:"/api/v3/admin/group/enrollment",
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function(data) {
                    $('#advanced-key').val('');
                }
            })
            $('#advanced-key').hide();
            $('.btn-copy-advanced').hide();
        }).on('pnotify.cancel', function() {
            $('#advanced-check').iCheck('check');
            $('#advanced-key').show();
            $('.btn-copy-advanced').show();
        });
    });

    $('#user-check').unbind('ifChecked').on('ifChecked', function(event){
        if($('#user-key').val()==''){
            const data = {}
            data['id']=$('#modalEnrollmentForm #id').val();
            data['role']="user";
            data['action']="reset";
            $.ajax({
                type: "POST",
                url:"/api/v3/admin/group/enrollment",
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function(data){
                    $('#user-key').val(data);
                }
            });
            $('#user-key').show();
            $('.btn-copy-user').show();
        }
    });
            
    $('#user-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
        const data = {}
        data['id']=$('#modalEnrollmentForm #id').val();
        data['role']="user";
        data['action']="disable";
        new PNotify({
            title: 'Confirmation Needed',
            text: "Are you sure you want to delete user code?",
            hide: false,
            opacity: 0.9,
            confirm: {
                confirm: true
            },
            buttons: {
                closer: false,
                sticker: false
            },
            history: {
                history: false
            },
            addclass: 'pnotify-center'
        }).get().on('pnotify.confirm', function() {
            pk=$('#modalEnrollmentForm #id').val();
            $.ajax({
                type: "POST",
                url:"/api/v3/admin/group/enrollment",
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function(data) {
                    $('#user-key').val('');
                }
            })
            $('#user-key').hide();
            $('.btn-copy-user').hide();
        }).on('pnotify.cancel', function() {
            $('#user-check').iCheck('check');
            $('#user-key').show();
            $('.btn-copy-user').show();
        });
    });

    $('.btn-copy-manager').on('click', function () {
        $('#manager-key').prop('disabled',false).select().prop('disabled',true);
        document.execCommand("copy");
    });
    $('.btn-copy-advanced').on('click', function () {
        $('#advanced-key').prop('disabled',false).select().prop('disabled',true);
        document.execCommand("copy");
    });
    $('.btn-copy-user').on('click', function () {
        $('#user-key').prop('disabled',false).select().prop('disabled',true);
        document.execCommand("copy");
    });
}