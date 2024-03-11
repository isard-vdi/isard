//   Copyright © 2017-2024 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases, Pau Abril Iranzo
//
//   This file is part of IsardVDI.
//
//   IsardVDI is free software: you can redistribute it and/or modify
//   it under the terms of the GNU Affero General Public License as published by
//   the Free Software Foundation, either version 3 of the License, or (at your
//   option) any later version.
//
//   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
//   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
//   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
//   details.
//
//   You should have received a copy of the GNU Affero General Public License
//   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
//
// SPDX-License-Identifier: AGPL-3.0-or-later

$(document).ready(function() {
    $template = $(".template-media-detail");
    modal_add_install = $('#modal_add_install').DataTable()
    initialize_modal_all_install_events()
    $('.btn-new').on('click', function () {
        if($('.quota-isos .perc').text() >=100){
            new PNotify({
                title: "Quota for adding CD/DVD.",
                    text: "Can't and another ISO, user quota full.",
                    hide: true,
                    delay: 3000,
                    icon: 'fa fa-alert-sign',
                    opacity: 1,
                    type: 'error'
                });
        }else if($('.limits-isos-bar').attr('aria-valuenow') >=100){
            new PNotify({
                title: "Quota for adding CD/DVD..",
                    text: "Can't add another ISO, category quota full.",
                    hide: true,
                    delay: 3000,
                    icon: 'fa fa-alert-sign',
                    opacity: 1,
                    type: 'error'
                });
        }else{
            $("#modalAddMediaForm")[0].reset();
            $('#modalAddMedia').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            $('#modalAddMediaForm').parsley();
            $('#modalAddMediaForm #name').focus(function(){
                if($(this).val()=='' && $('#modalAddMediaForm #url').val() !=''){
                    $(this).val($('#modalAddMediaForm #url').val().split('/').pop(-1));
                }
            });
            setAlloweds_add('#modalAddMediaForm #alloweds-add');
        }
    });

    $('.btn-new-local').on('click', function () {
            $("#modal-add-media-form-local")[0].reset();
            $('#modalAddMediaLocal').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');

            $('#modal-add-media-form-local').parsley();
            setAlloweds_add('#modalAddMediaLocal #upload-alloweds-add');
    });
    
    let tableId = '#media'
    if ($.fn.DataTable.isDataTable(tableId)) {
        $(tableId).DataTable().destroy();
        $(tableId).empty();
    }

    mediaReady = createDatatable(tableId, 'Downloaded')
    adminShowIdCol(mediaReady)


    $(tableId + " tbody").off('click').on('click', 'button', function () {
        let tr = $(this).closest("tr")
        let row = mediaReady.row(tr)
        switch ($(this).attr('id')) {
            case 'btn-details':
                showRowDetails(mediaReady, tr, row);
                break;
            case 'btn-check':
            case 'btn-delete':
            case 'btn-abort':
            case 'btn-download':
            case 'btn-alloweds':
            case 'btn-createfromiso':
            case 'btn-owner':
                showActions(mediaOtherTable, tr, row, $(this));
                break;
        }
    })

    $.ajax({
        type: "GET",
        url: "/api/v3/media/status",
        success: function (data) {
            $('#status').removeAttr('disabled')
            let notShownStatus = ['Downloaded']
            let status = data.filter((s) => !notShownStatus.includes(s.status))
            $.each(status, function (index, currentStatus) {
                $('#status').append($('<option>', {
                    value: currentStatus.status,
                    text: `${currentStatus.status} (${currentStatus.count} items)`
                }));
            })
        }
    });

    newStatus = null

    function handleStatusChange(event) {
        newStatus = event.target.value 

        let tableId = '#mediaOtherTable'
        if ($.fn.DataTable.isDataTable(tableId)) {
            $(tableId).DataTable().destroy();
            $(tableId).empty();
        }

        mediaOtherTable = createDatatable(tableId, newStatus)

        adminShowIdCol(mediaOtherTable)

        $(tableId + " tbody").off('click').on('click', 'button', function () {
            let tr = $(this).closest("tr")
            let row = mediaOtherTable.row(tr)
            switch ($(this).attr('id')) {
                case 'btn-details':
                    showRowDetails(mediaOtherTable, tr, row);
                    break;
                case 'bnt-check':
                case 'btn-delete':
                case 'btn-abort':
                case 'btn-download':
                case 'btn-alloweds':
                case 'btn-createfromiso':
                case 'btn-owner':
                    showActions(mediaOtherTable, tr, row, $(this));
                    break;
            }
        })
    }

    $('#status').on('change', handleStatusChange);


    $("#modalChangeOwnerMedia #send").off('click').on('click', function (e) {
        var form = $('#modalChangeOwnerMediaForm');
        data = form.serializeObject();
        let pk = $('#modalChangeOwnerMediaForm #id').val()
        $.ajax({
            type: "PUT",
            url:`/api/v3/media/owner/${pk}/${data['new_owner']}`,
            contentType: 'application/json',
            success: function(data)
            {
                $('form').each(function () { this.reset() });
                $('.modal').modal('hide');
                new PNotify({
                    title: "Owner changed succesfully",
                    text: "",
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-success',
                    opacity: 1,
                    type: "success"
                });
                mediaReady.ajax.reload();
                mediaOtherTable.ajax.reload();
            },
            error: function (data) {
                new PNotify({
                    title: "ERROR",
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 15000,
                    opacity: 1
                });
            }
        });
    });

    $("#modalAddMedia #send").on('click', function(e){
            var form = $('#modalAddMediaForm');

            form.parsley().validate();

            if (form.parsley().isValid()){
                data=$('#modalAddMediaForm').serializeObject();
                data=replaceAlloweds_arrays('#modalAddMediaForm #alloweds-add',data)
                data["detail"] = "Downloaded from website"
                data["hypervisors_pools"] = [data["hypervisors_pools"]]
                var notice = new PNotify({
                    text: 'Downloading...',
                    hide: true,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: "POST",
                    url:"/api/v3/media",
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    error: function (data) {
                        notice.update({
                            title: "ERROR creating media",
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 15000,
                            opacity: 1
                        });
                    },
                    success: function(data)
                    {
                        $('form').each(function() { this.reset() });
                        $('.modal').modal('hide');
                        notice.update({
                            title: "Created",
                            text: 'Media created successfully',
                            hide: true,
                            delay: 2000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                    }
                });
            }
        });

        $('#modalDeleteMedia #send').on('click', function(e) {
            media_id = $('#modalDeleteMediaForm #id').val()

            var notice = new PNotify({
                text: 'Deleting media...',
                hide: false,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })

            $.ajax({
                type: 'DELETE',
                url: '/api/v3/media/'+media_id,
                error: function(data) {
                    notice.update({
                        title: 'ERROR deleting media',
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                },
                success: function(data) {
                    $('form').each(function() {
                        this.reset()
                    })
                    $('.modal').modal('hide')
                    notice.remove()
                }
            })
        });

        if( $("#media_physical").length != 0){
            var media_physical=$('#media_physical').DataTable( {
              "ajax": {
              "url": "/api/v3/admin/storage/physical/media",
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
                    { "data": "path",},
                    { "data": "kind",},
                    { "data": "size"},
                    { "data": "hyper",},
              ],
              "columnDefs": [],
            });

            $(".btn-phy-update").on("click", function () {
                new PNotify({
                  title: "Rescan physical media on storage",
                  text: "Do you really want to rescan all them?",
                  hide: false,
                  opacity: 0.9,
                  confirm: { confirm: true },
                  buttons: { closer: false, sticker: false },
                  history: { history: false },
                  addclass: "pnotify-center",
                })
                  .get()
                  .on("pnotify.confirm", function () {
                    $.ajax({
                      type: "GET",
                      url:
                        "/api/v3/admin/storage/physical/storage_host",
                      contentType: "application/json",
                      success: function (storage_host) {
                        $.ajax({
                          type: "PUT",
                          url: storage_host+"/storage/media",
                          contentType: "application/json",
                          success: function (data) {
                            media_physical.ajax.reload();
                            new PNotify({
                              title: "Updated",
                              text:  "Updated "+data.media+" media from "+storage_host,
                              hide: true,
                              delay: 5000,
                              opacity: 1,
                              type: 'success'
                          });
                          },
                        });
                      },
                    });
                  })
                  .on("pnotify.cancel", function () {});
              });
          }
    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
    function socketio_on(){
        socket.on('media_add', function(data){
            var data = JSON.parse(data);
            data = {...mediaReady.row("#"+data.id).data(),...data}
            dtUpdateInsert(mediaReady,data,false);
        });

        socket.on('media_update', function(data){
            var data = JSON.parse(data);
            data = {...mediaReady.row("#"+data.id).data(),...data}
            row = mediaOtherTable.row('#'+data.id).remove().draw();
            dtUpdateInsert(mediaReady,data,false);
        });
    
        socket.on('media_delete', function(data){
            var data = JSON.parse(data);
            var row = mediaReady.row('#'+data.id).remove().draw();
            new PNotify({
                    title: "Media deleted",
                    text: "Media "+data.name+" has been deleted",
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-success',
                    opacity: 1,
                    type: 'success'
            });
            if ('status' in data){
                handleStatusChange({target: {value: newStatus}})
            }
        });
    
        socket.on('result', function (data) {
            var data = JSON.parse(data);
            new PNotify({
                    title: data.title,
                    text: data.text,
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-'+data.icon,
                    opacity: 1,
                    type: data.type
            });
        });
    
        socket.on('add_form_result', function (data) {
            var data = JSON.parse(data);
            if(data.result){
                $("#modalAddMediaForm")[0].reset();
                $("#modalAddMedia").modal('hide');
                $("#modalAddFromMedia #modalAdd")[0].reset();
                $("#modalAddFromMedia").modal('hide');
            }
            new PNotify({
                    title: data.title,
                    text: data.text,
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-'+data.icon,
                    opacity: 1,
                    type: data.type
            });
        });
    
        socket.on('edit_form_result', function (data) {
            var data = JSON.parse(data);
            if(data.result){
                $("#modalEdit")[0].reset();
                $("#modalEditDesktop").modal('hide');
            }
            new PNotify({
                    title: data.title,
                    text: data.text,
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-'+data.icon,
                    opacity: 1,
                    type: data.type
            });
        });
    }
})


function createDatatable(tableId, status, initCompleteFn = null) {
    return $(tableId).DataTable({
        ajax: {
            url: `/api/v3/admin/media/${status}`,
            contentType: 'application/json',
            type: 'GET',
        },
        sAjaxDataProp: '',
        language: {
            loadingRecords: '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        rowId: 'id',
        deferRender: true,
        columns: [
            {
                className: "details-control",
                orderable: false,
                data: null,
                width: "10px",
                defaultContent: '<button id="btn-details" class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            {
                title: 'Icon',
                data: 'icon',
                width: '10px',
                render: function ( data, type, full, meta ) {
                    return renderIcon(full);
                }
            },
            {
                title: 'Name',
                data: 'name',
                render: function ( data, type, full, meta ) {
                    return renderName(full);
                }
            },
            {
                title: 'Status',
                data: 'status',
                filter: true,
                width: '10px', 
                "render": function ( data, type, full, meta ) {
                    return full.status;
                }
            },
            {
                title: 'Owner',
                data: 'username',
                width: '10px',
                render: function ( data, type, full, meta ) {
                    if(!('username' in full)){return full.user;}
                    return full.username;
                }
            },
            {
                title: 'Category',
                data: 'category_name',
            },
            {
                title: 'Group',
                data: 'group_name',
            },
            {
                title: 'Progress/Size',
                data: null,
                width: '150px',
                className: 'text-center',
                render: function ( data, type, full, meta ) {
                    if(full.status == 'Downloading'){
                        return renderProgress(full);
                    }else{
                        if('progress' in data && 'total' in data.progress){
                            return data.progress.total;
                        }else{
                            return '';
                        }
                    }
                }
            },
            {
                title: 'Domains',
                data: 'domains',
                defaultContent: 0,
                width: '80px',
            },
            {
                title: 'Actions',
                data: null,
                defaultContent: '',
                render: function ( data, type, full, meta ) {
                    const checkButtons = '<button id="btn-task" type="button" data-task="' + full.task + '" class="btn btn-pill-right btn-xs" title="Show last task info"><i class="fa fa-tasks" style="color:darkblue"></i></button> \
                        <button id="btn-check" type="button" data-id="' + full.id + '" class="btn btn-pill-right  btn-xs" title="Check media status"><i class="fa fa-refresh" style="color:darkgreen"></i></button>'
                    if(['Available', 'DownloadFailed', 'deleted'].includes(full.status)){
                        return checkButtons + '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button> \
                                <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                    }
                    if(full.status == 'DownloadFailedInvalidFormat'){
                        return checkButtons + '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                    }
                    if(full.status == 'Downloading'){
                        return checkButtons + '<button id="btn-abort" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-stop" style="color:darkred"></i></button>'
                    }
                    if(full.status == 'Downloaded' || full.status == 'Stopped'){
                        if(full.kind.startsWith('qcow')){
                            return '<button id="btn-createfromiso" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-desktop" style="color:darkgreen"></i></button> \
                                    <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                        }else{
                            return checkButtons + '<button id="btn-createfromiso" title="Create desktop from media" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-desktop" style="color:darkgreen"></i></button> \
                            <button id="btn-alloweds" title="Change allowed users" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button> \
                            <button id="btn-owner" title="Change owner" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-exchange" style="color:darkblue"></i></button> \
                            <button id="btn-delete" title="Delete media" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> '
                        }
                    }
                }
            },
            {
                title: 'Id',
                data: 'id',
                visible: false,
            },
        ],
    });
}

function showRowDetails(table, tr, row) {
    var rowData = row.data();

    if (row.child.isShown()) {
        row.child.hide();
        tr.removeClass('shown');
    } else {
        table.rows('.shown').every(function () {
            this.child.hide();
            $(this.node()).removeClass('shown');
        });
        
        row.child(format(rowData)).show();
        var id = rowData.id;
        
        childTable = $('#cl' + id).DataTable({
            dom: "t",
            ajax: {
                url: "/api/v3/admin/media/domains/" + id,
                contentType: "application/json",
                type: "GET",
            },
            sAjaxDataProp: "",
            language: {
                loadingRecords:
                '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
            },
            columns: [
                { data: "kind", title: "Kind" },
                { data: "name", title: "Name" },
                { data: "user_data.username", title: "User" },
                { data: "category_name", title: "Group" },
                { data: "group_name", title: "Category" },
                { data: "id", title: "Id" },
                {
                    data: null, title: "Link",
                    render: function (data) {
                        let kind = data.kind.charAt(0).toUpperCase() + data.kind.slice(1).replace(/_/g, ' ');
                        let link = '<a href="/isard-admin/admin/domains/render/' + kind + 's?searchDomainId=' + data.id + '"><b>' + kind[0] + ': </b>' + data.name + '</a>';
                        return link;
                    }
                },
            ],
            columnDefs: [
            ],
            order: [],
            select: false,
        });
        tr.addClass('shown')
    }
}

function showActions(table ,tr, row, button) {
    let data = row.data();
    switch(button.attr('id')){
        case 'btn-check':
            new PNotify({
                title: "Check media status",
                text: "Do you really want to update the media status?",
                hide: false,
                opacity: 0.9,
                confirm: { confirm: true },
                buttons: { closer: false, sticker: false },
                history: { history: false },
                addclass: "pnotify-center",
            }).get().on('pnotify.confirm', function () {
                $.ajax({
                    type: "PUT",
                    url: '/api/v3/media/check/' + data['id'],
                    error: function (data) {
                        new PNotify({
                            title: "ERROR checking the media status",
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 15000,
                            opacity: 1
                        });
                    },
                    success: function (data) {
                        $('form').each(function () { this.reset() });
                        $('.modal').modal('hide');
                        new PNotify({
                            title: "Checked",
                            text: 'Media status checked successfully',
                            hide: true,
                            delay: 2000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                    }
                })
            }).on('pnotify.cancel', function () {
            });
            break;
        case 'btn-delete':
            $("#modalDeleteMediaForm")[0];
            $('#modalDeleteMediaForm #id').val(data['id']);
            $('#modalDeleteMedia').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            $.ajax({
                type: "GET",
                url: "/api/v3/media/desktops/"+data['id'],
            }).done(function(domains) {
                $('#table_modal_media_delete tbody').empty()
                $.each(domains, function(key, value) {
                    infoDomains(value, $('#table_modal_media_delete tbody'));
                });
            });
            break;
        case 'btn-abort':
                new PNotify({
                    title: 'Confirmation Needed',
                    text: "Are you sure you want to abort this download: "+data.name+"?",
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
                    $.ajax({
                        type: "POST",
                        url:"/api/v3/media/abort/" + data['id'],
                    });
                }).on('pnotify.cancel', function() {
                });
                break;
        case 'btn-download':
                new PNotify({
                    title: 'Confirmation Needed',
                    text: "Do you want to reload the download for "+data.name+"?",
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
                    $.ajax({
                        type: "POST",
                        url:"/api/v3/media/download/" + data['id'],
                    });
                }).on('pnotify.cancel', function() {
                });
                break;
        case 'btn-alloweds':
                modalAllowedsFormShow('media',data)
                break;
        case 'btn-createfromiso':
            if($('.quota-desktops .perc').text() >=100){
                new PNotify({
                    title: "Quota for creating desktops full.",
                    text: "Can't create another desktop, user quota full.",
                    hide: true,
                    delay: 3000,
                    icon: 'fa fa-alert-sign',
                    opacity: 1,
                    type: 'error'
                });
            }else if($('.limits-desktops-bar').attr('aria-valuenow') >=100){
                new PNotify({
                    title: "Quota for creating desktops full.",
                    text: "Can't create another desktop, category quota full.",
                    hide: true,
                    delay: 3000,
                    icon: 'fa fa-alert-sign',
                    opacity: 1,
                    type: 'error'
                });
            }else{
                $("#modalAddFromMedia #modalAdd")[0].reset();
                setHardwareOptions('#modalAddFromMedia','iso');
                $('#modalAddFromMedia #modalAdd #media').val(data.id);
                $('#modalAddFromMedia #modalAdd #kind').val(data.kind);
                if(data.kind.startsWith('qcow')){
                    $('#modalAddFromMedia #modalAdd #disk_size').hide();
                }else{
                    $('#modalAddFromMedia #modalAdd #disk_size').show()
                }
                $('#modalAddFromMedia #modalAdd #media_name').html(data.name);
                $('#modalAddFromMedia #modalAdd #media_size').html(data.progress.total);
                $('#modalAddFromMedia').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');

                $('#modalAddFromMedia #modalAdd').parsley();
                modal_add_install_datatables();
            }
            break;
        case 'btn-owner':
            var pk = data.id
            $("#modalChangeOwnerMediaForm")[0].reset();
            $('#modalChangeOwnerMedia').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            $('#modalChangeOwnerMediaForm #id').val(pk);
            $("#new_owner").val("");
            if($("#new_owner").data('select2')){
                $("#new_owner").select2('destroy');
            }
            $('#new_owner').select2({
                placeholder:"Type at least 2 letters to search.",
                minimumInputLength: 2,
                dropdownParent: $('#modalChangeOwnerMedia'),
                ajax: {
                    type: "POST",
                    url: '/admin/allowed/term/users',
                    dataType: 'json',
                    contentType: "application/json",
                    delay: 250,
                    data: function (params) {
                        return  JSON.stringify({
                            term: params.term,
                            pluck: ['id','name']
                        });
                    },
                    processResults: function (data) {
                        return {
                            results: $.map(data, function (item, i) {
                                return {
                                    text: item.name + '['+item['uid']+'] ',
                                    id: item.id
                                }
                            })
                        };
                    }
                },
            });
            break;
    }; 
}

function renderProgress(data){
            perc = data.progress.received_percent
            return data.progress.total+' - '+data.progress.speed_download_average+'/s - '+data.progress.time_left+'<div class="progress"> \
                  <div id="pbid_'+data.id+'" class="progress-bar" role="progressbar" aria-valuenow="'+perc+'" \
                  aria-valuemin="0" aria-valuemax="100" style="width:'+perc+'%"> \
                    '+perc+'%  \
                  </div> \
                </<div> '
}

function renderName(data){
        return '<div class="block_content" > \
                  <h4 class="title" style="height: 4px; margin-top: 0px;"> \
                <a>'+data.name+'</a> \
                </h4> \
                  <p class="excerpt" >'+data.description+'</p> \
                   </div>'
}

function renderIcon(data){
    return '<span class="xe-icon" data-pk="'+data.id+'">'+icon(data.icon)+'</span>'
}

function icon(name){
    if(name.startsWith("fa-")){return "<i class='fa "+name+" fa-2x '></i>";}
    if(name.startsWith("fl-")){return "<span class='"+name+" fa-2x'></span>";}
       if(name=='windows' || name=='linux'){
           return "<i class='fa fa-"+name+" fa-2x '></i>";
        }else{
            return "<span class='fl-"+name+" fa-2x'></span>";
        }
}


// MODAL install FUNCTIONS
function initialize_modal_all_install_events(){
   $('#modal_add_install tbody').on( 'click', 'tr', function () {
        rdata=modal_add_install.row(this).data()
        if ( $(this).hasClass('selected') ) {
            $(this).removeClass('selected');
            show_no_os_hardware_template_selected()
            $('#modalInstall #install').val('');
        }
        else {
            modal_add_install.$('tr.selected').removeClass('selected');
            $(this).addClass('selected');
            $('#modal_add_install').closest('.x_panel').removeClass('datatables-error');
            $('#modalInstall #datatables-install-error-status').empty().removeClass('my-error');   //.html('Selected: '+rdata['name']+'')
            $('#modalInstall #install').val(rdata['id']);
        }
    } );
}

function modal_add_install_datatables(){
    modal_add_install.destroy()
    $('#modalInstall #install').val('');
    $('#modalInstall #datatables-error-status').empty()

    $('#modal_add_install thead th').each( function () {
        var title = $(this).text();
        if(title=='Name'){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );

    modal_add_install = $('#modal_add_install').DataTable({
        "ajax": {
            "url": "/api/v3/media/installs",
            "dataSrc": ""
        },
        "scrollY":        "125px",
        "scrollCollapse": true,
        "paging":         false,
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
            "zeroRecords":    "No matching templates found",
            "info":           "Showing _START_ to _END_ of _TOTAL_ templates",
            "infoEmpty":      "Showing 0 to 0 of 0 templates",
            "infoFiltered":   "(filtered from _MAX_ total templates)"
        },
        "rowId": "id",
        "deferRender": true,
        "columns": [
            { "data": "name"},
            { "data": "vers"},
        ],
        "order": [[0, 'asc']],
        "pageLength": 10,
    } );

    modal_add_install.columns().every( function () {
        var that = this;

        $( 'input', this.header() ).on( 'keyup change', function () {
            if ( that.search() !== this.value ) {
                that
                    .search( this.value )
                    .draw();
            }
        } );
    } );

    $("#modalAddFromMedia #send").off('click').on('click', function(e){
        var form = $('#modalAddFromMedia #modalAdd');
        form.parsley().validate();

        if (form.parsley().isValid()){
            install=$('#modalAddFromMedia #install').val();
            if (install !=''){
                data=$('#modalAddFromMedia #modalAdd').serializeObject();
                data=parse_media(JSON.unflatten(data));
                var notice = new PNotify({
                    text: 'Creating desktop...',
                    hide: true,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: "POST",
                    url:"/api/v3/desktop/from/media",
                    contentType: "application/json",
                    data: JSON.stringify(data),
                    error: function(data){
                        notice.update({
                            title: "ERROR creating desktop",
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 15000,
                            opacity: 1
                        });
                    },
                    success: function(data) {
                        $('form').each(function() { this.reset() });
                        $('.modal').modal('hide');
                        notice.update({
                            title: "New desktop",
                            text: 'Desktop created successfully',
                            hide: true,
                            delay: 2000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                    }
                });
            }else{
                show_no_os_hardware_template_selected()
            }
        }
        });
}

function parse_media(data){
    return {"media_id":data["media"],
        "xml_id":data["install"],
        "kind":data["kind"],
        "name":data["name"],
        "description":data["description"],
        "hardware": {
            ...("vcpus" in data["hardware"]) && {"vcpus": parseInt(data["hardware"]["vcpus"])},
            ...("memory" in data["hardware"]) && {"memory": parseFloat(data["hardware"]["memory"])},
            ...("videos" in data["hardware"]) && {"videos": [data["hardware"]["videos"]]},
            ...("boot_order" in data["hardware"]) && {"boot_order": [data["hardware"]["boot_order"]]},
            ...("interfaces" in data["hardware"]) && {"interfaces": data["hardware"]["interfaces"]},
            ...("disk_bus" in data["hardware"]) && {"disk_bus": data["hardware"]["disk_bus"]},
            ...("disk_size" in data) && {"disk_size": parseInt(data["disk_size"])},
        },
    }
}

function format(rowData) {
    var childTable =
      '<table id="cl' +
      rowData.id +
      '" class="display compact nowrap w-100" width="100%">' +
      "</table>";
    return $(childTable).toArray();
}
