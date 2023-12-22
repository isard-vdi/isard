/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var table = ''

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

    table=$('#media').DataTable( {
        "ajax": {
                "url": "/api/v3/admin/table/media",
                "contentType": "application/json",
                "type": 'POST',
                "data": function(d){return JSON.stringify({'flatten':false})}
        },
        "sAjaxDataProp": "",
            "language": {
                "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
            },
            "rowId": "id",
            "deferRender": true,
        "columns": [
            {
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "icon", "width": "10px"},
            { "data": "name",},
            { "data": "status", "width": "10px"},
            { "data": null, "width": "10px"},
            { "data": "category_name", "width": "10px"},
            { "data": "group_name", "width": "10px"},
            { "data": null,"width": "150px", "className": "text-center"},
            { "data": "domains", 'defaultContent': 0,"width": "80px"},
            { "data": null, 'defaultContent': ''},
            { "data": "id", "visible": false},
        ],
        "columnDefs": [
                            {
                            "targets": 1,
                            "render": function ( data, type, full, meta ) {
                              return renderIcon(full);
                            }},
                            {
                            "targets": 2,
                            "render": function ( data, type, full, meta ) {
                              return renderName(full);
                            }},
                            {
                                "targets": 3,
                                "render": function ( data, type, full, meta ) {
                                  return full.status;
                                }},
                            {
                            "targets": 4,
                            "render": function ( data, type, full, meta ) {
                                if(!('username' in full)){return full.user;}
                              return full.username;
                            }},
                            {
                                "targets": 7,
                                "render": function ( data, type, full, meta ) {
                                    if(full.status == 'Downloading'){
                                        return renderProgress(full);
                                    }else{
                                        if('progress' in data && 'total' in data.progress){
                                            return data.progress.total;
                                        }else{
                                            return '';
                                        }
                                    }
                                }},
                            {
                            "targets": 9,
                            "render": function ( data, type, full, meta ) {
                                    if(['Available', 'DownloadFailed', 'deleted'].includes(full.status)){
                                        return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button> \
                                                <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                    }
                                    if(full.status == 'DownloadFailedInvalidFormat'){
                                        return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                    }
                                    if(full.status == 'Downloading'){
                                        return '<button id="btn-abort" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-stop" style="color:darkred"></i></button>'
                                    }
                                    if(full.status == 'Downloaded' || full.status == 'Stopped'){
                                        if(full.kind.startsWith('qcow')){
                                            return '<button id="btn-createfromiso" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-desktop" style="color:darkgreen"></i></button> \
                                                    <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                        }else{
                                            return '<button id="btn-createfromiso" title="Create desktop from media" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-desktop" style="color:darkgreen"></i></button> \
                                            <button id="btn-alloweds" title="Change allowed users" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button> \
                                            <button id="btn-owner" title="Change owner" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-exchange" style="color:darkblue"></i></button> \
                                            <button id="btn-delete" title="Delete media" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> '
                                        }
                                }
                                }}],
    } );

    adminShowIdCol(table)

    $('#media tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest("tr");
        var row = table.row(tr);
        var rowData = row.data();

        if (row.child.isShown()) {
          // This row is already open - close it
          row.child.hide();
          tr.removeClass("shown");
        //   table.ajax.reload();

          // Destroy the Child Datatable
          $("#cl" + rowData.clientID)
            .DataTable()
            .destroy();
        } else {
            // Open this row
            row.child(format(rowData)).show();
            var id = rowData.id;

            childTable = $("#cl" + id).DataTable({
              dom: "t",
              ajax: {
                url: "/admin/media/domains/" + id,
                contentType: "application/json",
                type: "GET",
              },
              sAjaxDataProp: "",
              language: {
                loadingRecords:
                  '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
              },
              columns: [
                { data: "kind" },
                { data: "name" },
              ],
              columnDefs: [
              ],
              select: false,
            });
            tr.addClass("shown");
          }
    } );

    $('#media').find(' tbody').on( 'click', 'button', function () {
        data = table.row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
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
    });

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
                table.ajax.reload();
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
            data = {...table.row("#"+data.id).data(),...data}
            dtUpdateInsert(table,data,false);
        });

        socket.on('media_update', function(data){
            var data = JSON.parse(data);
            data = {...table.row("#"+data.id).data(),...data}
            dtUpdateInsert(table,data,false);
        });
    
        socket.on('media_delete', function(data){
            //~ console.log('delete')
            var data = JSON.parse(data);
            var row = table.row('#'+data.id).remove().draw();
            new PNotify({
                    title: "Media deleted",
                    text: "Media "+data.name+" has been deleted",
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-success',
                    opacity: 1,
                    type: 'success'
            });
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