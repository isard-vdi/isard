//
//   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
//   Copyright (C) 2023
//
//   This program is free software: you can redistribute it and/or modify
//   it under the terms of the GNU Affero General Public License as published by
//   the Free Software Foundation, either version 3 of the License, or
//   (at your option) any later version.
//
//   This program is distributed in the hope that it will be useful,
//   but WITHOUT ANY WARRANTY; without even the implied warranty of
//   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
//   GNU Affero General Public License for more details.
//
//   You should have received a copy of the GNU Affero General Public License
//   along with this program. If not, see <https://www.gnu.org/licenses/>.
//
// SPDX-License-Identifier: AGPL-3.0-or-later


$(document).ready(function () {
    personalunits_table = $('#table-personalunits').DataTable({
        "ajax": {
            "url": "/api/v3/admin/user_storage",
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
                "defaultContent": '' //'<button id="btn-details" class="btn btn-xs btn-info" type="button" data-placement="top"><i class="fa fa-plus"></i></button>'
            },
            { "data": "enabled" },
            { "data": "provider" },
            { "data": "name" },
            { "data": "description" },
            { "data": "category_names" },
            { "data": "authorization" },
            { "data": "connection" },
            { "data": "verify_cert" },
            { "data": null, "width": "100px","orderable": false, "defaultContent": '<i class="fa fa-spinner fa-pulse fa-fw"></i><span class="sr-only">...</span>'},
            { "data": null, "width": "75px" },
            { "data": "id", "visible": false },
        ],
        "order": [[1, 'asc']],
        "columnDefs":[
            {
                "targets": 1,
                "render": function ( data, type, full, meta ) {
                    if (full.enabled) {
                        return '<i class="fa fa-circle" aria-hidden="true" style="color:green" title="' + full.enabled + '"></i>'
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true" style="color:darkgray"></i>'
                    }
                }
            },
            {
                "targets": 5,
                "render": function ( data, type, full, meta ) {
                    return full.category_names == [] ? "Everyone" : full.category_names.join(", ");
                }
            },
            {
                "targets": 6,
                "render": function ( data, type, full, meta ) {
                    if (full.authorization) {
                        return '<i class="fa fa-circle" aria-hidden="true" style="color:green" title="Authorization keys found"></i>'
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true" style="color:darkgray"></i>  \
                        <button id="btn-login_auth" class="btn btn-xs" type="button" data-placement="top"><i class="fa fa-user" style="color:orange" title="Authorize client"></i> Authorize</button>'
                    }
                }
            },
            {
                "targets": 7,
                "render": function ( data, type, full, meta ) {
                    if ( ! full.hasOwnProperty('connection') ) {
                        return '<i class="fa fa-spinner fa-pulse fa-fw"></i><span class="sr-only">...</span>'
                    }
                    if (full.connection) {
                        return '<i class="fa fa-circle" aria-hidden="true" style="color:green" title="Can reach and authorize clien"></i>'
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true" style="color:darkgray"></i>'
                    }
                }
            },
            {
                "targets": 5,
                "render": function ( data, type, full, meta ) {
                    return full.category_name == "*" ? "Everyone" : full.category_name;
                }
            },
            {
                "targets": 8,
                "render": function ( data, type, full, meta ) {
                    if ('verify_cert' && full.verify_cert) {
                        return '<i class="fa fa-circle" aria-hidden="true" style="color:green" title="' + full.verify_cert + '"></i>'
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true" style="color:darkgray"></i>'
                    }
                }
            },
            {
                "targets": 9,
                "render": function ( data, type, full, meta ) {
                    if ( full.hasOwnProperty('new_users') ) {
                        toshow = ""
                        if ( full.new_users > 0 ) {
                            toshow += '<i class="fa fa-user-plus" aria-hidden="true" style="color:orange" title="New users"></i> '+full.new_users+' New<br>'
                        }
                        if ( full.deleted_users > 0 ) {
                            toshow += '<i class="fa fa-user-times" aria-hidden="true" style="color:orange" title="Deleted users"></i> '+full.deleted_users+' Deleted<br>'
                        }
                        if ( full.new_groups > 0 ) {
                            toshow += '<i class="fa fa-users" aria-hidden="true" style="color:orange" title="New groups"></i> '+full.new_groups+' New<br>'
                        }
                        if ( full.deleted_groups > 0 ) {
                            toshow += '<i class="fa fa-users" aria-hidden="true" style="color:orange" title="Deleted groups"></i> '+full.deleted_groups+' Deleted<br>'
                        }
                        if ( toshow == "" ) {
                            toshow = '<i class="fa fa-check" aria-hidden="true" style="color:green" title="Everything is ok"></i>'
                        }else{
                            // Add red warning icon inside button
                            toshow += '<button id="btn-sync" class="btn btn-xs" type="button" data-placement="top"><i class="fa fa-refresh" style="color:darkred" title="Synchronize"></i></button>'
                        }
                        return toshow
                    }
                }
            },
            {
                "targets": 10,
                "render": function ( data, type, full, meta ) {
                    if (full.enabled && full.connection && full.authorization) {
                        buttons = '<button id="btn-reset-data" class="btn btn-xs" type="button" data-placement="top"><i class="fa fa-users" style="color:darkred" title="Reset users"></i></button> \
                        <button id="btn-delete" class="btn btn-xs" type="button" data-placement="top"><i class="fa fa-trash" style="color:darkred" title="Delete"></i></button>'
                    } else {
                        buttons = '<button id="btn-delete" class="btn btn-xs" type="button" data-placement="top"><i class="fa fa-trash" style="color:darkred" title="Delete"></i></button>'
                    }
                    return buttons
                }
            }
        ]
    });



    function init_personalunits_table() {
        $('#personalunits-progress-log').DataTable().clear().destroy();
        personalunits_progress=$('#personalunits-progress-log').DataTable( {
            data: {},
            rowId: 'id',
            //~ language: {
                //~ "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
            //~ },
            columns: [
                { "data": "status"},
                { "data": "name", "defaultContent": ""},
                { "data": "msg", "defaultContent": ""},
                { "data": "action", "defaultContent": ""},
                ],
            "order": [[0, 'asc']],
            "columnDefs": [ 
                {
                    "targets": 0,
                    "render": function ( data, type, full, meta ) {
                        if(full.status == true){
                            return '<i class="fa fa-check" style="color:darkgreen"></i>';
                        }else{
                            return '<i class="fa fa-close" style="color:darkred"></i>';
                        }
                    }
                }
            ]
        });
    }

    adminShowIdCol(personalunits_table)

    $('#table-personalunits tbody').on( 'click', 'button', function () {
        tr = $(this).closest("tr");
        row = personalunits_table.row(tr)    
        data = row.data();
        switch($(this).attr('id')){
            case 'btn-details':
                if (row.child.isShown()) {
                    row.child.hide();
                    tr.removeClass("shown");
                } else {
                    tr.addClass('shown');
                    if (personalunits_table.row('.shown').length) {
                        $('.details-control', personalunits_table.row('.shown').node()).click();
                    }
                    row.child(renderPersonalUnitsDetails(row.data())).show()
                    // setAlloweds_viewer('#alloweds-' + row.data().id, row.data().id, "storage_pool");
                }
            break;
            case 'btn-delete':
                new PNotify({
                    title: '<b>WARNING</b>',
                    type: "error",
                    text: "<b>All users and their current data in storage provider will be lost.\nAre you sure you want to delete provider '"+data['name']+"'?</b>",
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
                    addclass: 'pnotify-center-large',
                    width: '550'
                }).get().on('pnotify.confirm', function() {
                    $.ajax({
                        type: "DELETE",
                        url: "/api/v3/admin/user_storage/" + data["id"],
                        success: function (data) {
                            $('form').each(function () { this.reset() });
                            $('.modal').modal('hide');
                            personalunits_table.ajax.reload();
                        },
                        error: function (xhr, ajaxOptions, thrownError) {
                            new PNotify({
                                title: "ERROR deleting provider",
                                text: xhr.responseJSON.description,
                                hide: true,
                                delay: 3000,
                                icon: 'fa fa-warning',
                                opacity: 1,
                                type: 'error'
                            });
                        }
                    });
                }).on('pnotify.cancel', function() {});	
                break;
            case 'btn-sync':
                $("#modalPersonalunitsProgressForm")[0].reset();
                $('#btn-personalunit-syncusers').prop('disabled', false);
                $('#spinner_sync_users').hide();
                $('#btn-personalunit-syncgroups').prop('disabled', false);
                $('#spinner_sync_groups').hide();
                init_personalunits_table();
                $('#modalPersonalunitsProgress').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');
                $('#modalPersonalunitsProgressForm #id').val(data.id);
                break;
            case 'btn-reset-data':
                new PNotify({
                    title: '<b>WARNING: RESET PROVIDER DATA</b>',
                    type: "error",
                    text: "<b>All users and their current data in storage provider will be lost.\nAre you sure you want to delete users and groups in '"+data['name']+"'?</b>",
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
                    addclass: 'pnotify-center-large',
                    width: '550'
                }).get().on('pnotify.confirm', function() {
                    $.ajax({
                        type: "DELETE",
                        url: "/api/v3/admin/user_storage/" + data["id"]+"/reset",
                        success: function (data) {
                            $('form').each(function () { this.reset() });
                            $('.modal').modal('hide');
                            personalunits_table.ajax.reload();
                        },
                        error: function (xhr, ajaxOptions, thrownError) {
                            new PNotify({
                                title: "ERROR deleting provider",
                                text: xhr.responseJSON.description,
                                hide: true,
                                delay: 3000,
                                icon: 'fa fa-warning',
                                opacity: 1,
                                type: 'error'
                            });
                        }
                    });
                }).on('pnotify.cancel', function() {});	
                break;
                case 'btn-login_auth':
                    new PNotify({
                        title: '<b>AUTHORIZE PROVIDER</b>',
                        type: "warning",
                        text: "<b>This will open your provider login page where you should input your admin credentials.</b>",
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
                        addclass: 'pnotify-center-large',
                        width: '550'
                    }).get().on('pnotify.confirm', function() {
                        $.ajax({
                            type: "GET",
                            url: "/api/v3/admin/user_storage/" + data["id"]+"/login_auth",
                            success: function (data) {
                                data = JSON.parse(data);
                                window.open(data.login_url, '_blank');
                            },
                            error: function (xhr, ajaxOptions, thrownError) {
                                new PNotify({
                                    title: "ERROR contacting provider. Check data and try again.",
                                    text: xhr.responseJSON.description,
                                    hide: true,
                                    delay: 3000,
                                    icon: 'fa fa-warning',
                                    opacity: 1,
                                    type: 'error'
                                });
                            }
                        });
                    }).on('pnotify.cancel', function() {});	
                    break;
        }
    });      

    $('#btn-personalunit-syncusers').on( 'click', function () {
        id=$('#modalPersonalunitsProgressForm #id').val();
        $(this).prop("disabled", true);
        $("#spinner_sync_users").show();
        $.ajax({
            type: "PUT",
            url: "/api/v3/admin/user_storage/"+id+"/sync/users",
            contentType: "application/json",
            success: function () {
                new PNotify({
                    title: "Sync Users",
                    text: "Syncing...",
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-info',
                    opacity: 1,
                    type: 'info'
                });
            },
            error: function (xhr, ajaxOptions, thrownError) {
                new PNotify({
                    title: "Sync Users",
                    text: xhr.responseJSON.description,
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-alert',
                    opacity: 1,
                    type: 'error'
                });
            },
            complete: function(){
                $('#spinner_sync_users').hide();
                $('#btn-personalunit-syncusers').prop('disabled', false);
            }
        });
    });

    $('#btn-personalunit-syncgroups').on( 'click', function () {
        id=$('#modalPersonalunitsProgressForm #id').val();
        $(this).prop("disabled", true);
        $("#spinner_sync_groups").show();
        $.ajax({
            type: "PUT",
            url: "/api/v3/admin/user_storage/"+id+"/sync/groups",
            data: JSON.stringify({'id':id,'sync':'groups'}),
            contentType: "application/json",
            success: function () {
                new PNotify({
                    title: "Sync Groups",
                    text: "Syncing...",
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-info',
                    opacity: 1,
                    type: 'info'
                });
            },
            error: function (xhr, ajaxOptions, thrownError) {
                new PNotify({
                    title: "Sync Groups",
                    text: xhr.responseJSON.description,
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-alert',
                    opacity: 1,
                    type: 'error'
                });
            },
            complete: function(){
                $('#spinner_sync_groups').hide();
                $('#btn-personalunit-syncgroups').prop('disabled', false);
            }
        });
    });

    $('.add-new-personalunit').on( 'click', function () {
        $('#modalPersonalunitsForm #name').attr("disabled",false);
        $("#modalPersonalunitsForm")[0].reset();
        $('#btn-check-personal_unit').prop('disabled', false);
        $('#spinner_check_conn').hide();
        $('#modalPersonalunits').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalPersonalunitsForm #verify_cert').iCheck('check').iCheck('update')
        $.ajax({
            type: "POST",
            url: "/api/v3/admin/userschema",
            contentType: "application/json"
        }).done(function (data) {
            $('#modalPersonalunitsForm #access').find('option').remove().end();
            $('#modalPersonalunitsForm #access').append('<option value="">Choose</option>');
            $('#modalPersonalunitsForm #access').append('<option value="*">[All users]</option>');
            $('#table_modal_delete tbody').empty()

            $.each(data.category, function (key, value) {
                $('#modalPersonalunitsForm #access').append('<option value=' + value.id + '> Only ' + value.name + ' category</option>');
            });
        });
        $('#modalPersonalunits #modalPersonalunitsForm').parsley();
    });

    $("#modalPersonalunits #send").on('click', function(e){
        var form = $('#modalPersonalunitsForm');
        data = form.serializeObject()
        form.parsley().validate();
        if (form.parsley().isValid()){  
            if('verify_cert' in data){
                data['verify_cert']=true
            }else{
                data['verify_cert']=false
            }
            data["quota"]={"admin": parseInt(data["quota-admin"]), "manager": parseInt(data["quota-manager"]), "advanced": parseInt(data["quota-advanced"]), "user": parseInt(data["quota-user"])}
            $.ajax({
                type: "POST",
                url: "/api/v3/admin/user_storage/auth_basic",
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function () {
                    $('form').each(function () { this.reset() });
                    $('.modal').modal('hide');
                    personalunits_table.ajax.reload();
                },
                error: function (xhr, ajaxOptions, thrownError) {
                    new PNotify({
                        title: "Sync Users",
                        text: xhr.responseJSON.description,
                        hide: true,
                        delay: 4000,
                        icon: 'fa fa-alert',
                        opacity: 1,
                        type: 'error'
                    });
                }
            });
        }
    });

    user_storage_users = $('#table-user_storage_users').DataTable({
        "ajax": {
            "url": "/admin/user_storage/users",
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
            // {
            //     "className": 'details-control',
            //     "orderable": false,
            //     "data": null,
            //     "defaultContent": '<button id="btn-details" class="btn btn-xs btn-info" type="button" data-placement="top"><i class="fa fa-plus"></i></button>'
            // },
            { "data": "name" },
            { "data": "group_name" },
            { "data": "category_name" },
            { "data": "user_storage.provider_id" },
            { "data": "user_storage.provider_quota.quota" },
            { "data": "user_storage.provider_quota.total" },
            { "data": "user_storage.provider_quota.used" },
            { "data": "user_storage.provider_quota.relative" },
            { "data": "user_storage.provider_quota.free" },
            // {
            //     "className": 'actions-control',
            //     "orderable": false,
            //     "data": null,
            //     "defaultContent": '<button id="btn-edit" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
            // },
            { "data": "id", "visible": false },
        ],
        "order": [[1, 'asc']],
    });

    adminShowIdCol(user_storage_users)

    // Footer search columns
    $('#table-user_storage_users tfoot tr:first th').each( function () {
        var title = $(this).text();
        if ([''].indexOf(title) == -1){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );

    // Apply the search
    user_storage_users.columns().every( function () {
        var that = this;

        $( 'input', this.footer() ).on( 'keyup change', function () {
            if ( that.search() !== this.value ) {
                that.search( this.value ).draw();
            }
        } );
    } );

    $('#table-user_storage_users tbody').on( 'click', 'button', function () {
        tr = $(this).closest("tr");
        row = user_storage_users.row(tr)
        data = row.data();
        switch($(this).attr('id')){
            case 'btn-edit':
                $("#modalEditUsersQuota #modalEdit")[0].reset();
                $('#modalEditUsersQuota').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');
                $('#modalEditUsersQuota #modalEdit').parsley();
                $("#modalEdit #id").val(data.id);
                $("#modalEdit #name").val(data.name);
                break;
        }
    }); 

    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)

    function socketio_on(){
        socket.on('user_storage_provider', function(data){
            var data = JSON.parse(data);
            data = {...personalunits_table.row("#"+data.id).data(),...data}
            dtUpdateInsert(personalunits_table,data,false);
        });

        socket.on('personal_unit', function(data){
            var data = JSON.parse(data);
            if (typeof personalunits_progress !== 'undefined') {
                dtUpdateInsert(personalunits_progress,data,false);
            }
        });
    
        socket.on('result', function (data) {
            var data = JSON.parse(data);
            new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-' + data.icon,
                opacity: 1,
                type: data.type
            });
        });

        socket.on('delete', function (data) {
            var dict = JSON.parse(data);
            data = dict['data']
            switch (dict['table']) {
                case 'personalunits':
                    var row = personalunits_table.row('#'+data.id).remove().draw();
                    break;
            }
            new PNotify({
                title: "Deleted",
                text: data.name + " has been deleted",
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
            });
        });
    }
})



function renderPersonalUnitsDetails(data) {
    $newPanel = $(".template-user_storage-detail").clone();
    $quotaTBody = $newPanel.find("tbody");
    $quotaTBody.empty();
    $.each(data.quota, function(role, number) {
        $quotaTBody.append(
            $('<tr>').append(
                $('<td>').text(role),
                $('<td>').text(number)
            )
        );
    });
    // $newPanel.html(function(i, oldHtml){
    //   return oldHtml.replace(/d.id/g, data.id).replace(/d.name/g, data.name).replace(/d.description/g, data.description);
    // });
    return $newPanel;
}
