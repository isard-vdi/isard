/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

socket=null
user={}

$(document).on('shown.bs.modal', '#modalAddDesktop', function () {
    modal_add_desktops.columns.adjust().draw();
}); 

$(document).ready(function() {
    $('.admin-status').hide()
    user['role']=$('#user-data').data("role");
    $('.btn-delete-template').remove()
    modal_add_desktops = $('#modal_add_desktops').DataTable()
    initalize_modal_all_desktops_events()
    setViewerHelp();

    $template = $(".template-detail-domain");

    //DataTable Main renderer
    table = $('#desktops').DataTable({
            "ajax": {
                "url": "/api/v3/user/webapp_desktops",
                "dataSrc": ""
            },
            "language": {
                "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "<h1>You don't have any desktop created yet.</h1><br><h2>Create one using the +Add new button on top right of this page.</h2><br>\
                                Select your desktop from templates created and shared by the administrator."
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
                { "data": "icon", "width": "10px" },
                { "data": "server", "width": "10px", "defaultContent":"-"},
                { "data": null, "width": "10px"},
                { "data": null, "width": "10px"},
                { "data": "status", "width": "10px"},
                { "data": null, "width": "10px"},
                { "data": "name"},
                { "data": null, "width": "90px"},
                ],
             "order": [[3, 'desc']],
        "columnDefs": [ {
                            "targets": 1,
                            "render": function ( data, type, full, meta ) {
                                url = location.protocol+'//' + document.domain + ':' + location.port + full.image.url
                                return "<img src='"+url+"' width='50px'>"
                            }},
                            {
                            "targets": 2,
                            "render": function (data, type, full, meta) {
                                if('server' in full){
                                    return full['server']
                                }else{
                                    return false;
                                }
                            }},
                            {
                            "targets": 3,
                            "render": function ( data, type, full, meta ) {
                              return renderAction(full);
                            }},
                            {
                            "targets": 4,
                            "render": function ( data, type, full, meta ) {
                              return renderDisplay(full);
                            }},
                            {
                            "targets": 5,
                            "render": function ( data, type, full, meta ) {
                              return renderStatus(full,table);
                            }},
                            {
                            "targets": 6,
                            "render": function ( data, type, full, meta ) {
                                if(full["guest_properties"]["viewers"]["preferred"])
                                {return full["guest_properties"]["viewers"]["preferred"].replace('-','/');}
                              return '';
                            }},
                            {
                            "targets": 7,
                            "render": function ( data, type, full, meta ) {
                              return renderName(full);
                            }},
                            {
                            "targets": 8,
                            "render": function ( data, type, full, meta ) {
                              return renderMedia(full);
                            }},
                            //~ {
                            //~ "targets": 7,
                            //~ "render": function ( data, type, full, meta ) {
                              //~ return renderHotplugMedia(full);
                            //~ }}
                            ],
        "rowCallback": function (row, data) {
            if('server' in data){
                if(data['server'] == true){
                    $(row).css("background-color", "#f7eac6");
                }else{
                    $(row).css("background-color", "#ffffff");
                }
            }
        }
    } );

    // DataTable detail
    $('#desktops tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = table.row( tr );
        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            row.child.remove();
            tr.removeClass('shown');
        }
        else {
            // Close other rows
            if ( table.row( '.shown' ).length ) {
                    $('.details-control', table.row( '.shown' ).node()).click();
            }
            // Open this row
            row.child( addDesktopDetailPannel(row.data()) ).show();
            tr.addClass('shown');
            $('#status-detail-'+row.data().id).html(row.data().detail);
            actionsDesktopDetail();
            setDesktopDetailButtonsStatus(row.data().id,row.data().status, row.data().server)
            if(row.data().status=='Stopped' || row.data().status=='Started'){
                setDomainHotplug(row.data().id, row.data());
                setHardwareDomainDefaults_viewer('#hardware-'+row.data().id,row.data());
            }
          }
    } );

    // DataTable buttons
    $('#desktops tbody').on( 'click', 'button', function () {
        var data = table.row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
            case 'btn-play':
                if($('.quota-play .perc').text() >=100){
                    new PNotify({
                        title: "Quota for running desktops full.",
                            text: "Can't start another desktop, quota full.",
                            hide: true,
                            delay: 3000,
                            icon: 'fa fa-alert-sign',
                            opacity: 1,
                            type: 'error'
                        });
                }else{
                    api.ajax('/api/v3/desktop/start/' + data["id"], 'GET',{'pk':data['id'],'name':'status','value':'Starting'}).done(function(data) {});
                }          
                break;
            case 'btn-stop':
                if(data['status']=='Started'){
                    api.ajax('/api/v3/desktop/stop/' + data["id"], 'GET',{'pk':data['id'],'name':'status','value':'Shutting-down'}).done(function(data) {});
                }else{
                    new PNotify({
                        title: 'Unplug desktop warning!',
                            text: "It is NOT RECOMMENDED to continue and turn off desktop "+ name+".\n \
                                Please, properly shut down desktop from inside viewer \n\n \
                                Turn off desktop "+ name +"?",
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
                            api.ajax('/api/v3/desktop/stop/' + data["id"], 'GET',{'pk':data['id'],'name':'status','value':'Stopping'}).done(function(data) {});
                        }).on('pnotify.cancel', function() {
                    });
                }
                break;
            case 'btn-display':
                setViewerButtons(data,socket);

                if('viewer' in data && 'guest_ip' in data['viewer']){
                    viewerButtonsIP(data['viewer']['guest_ip'])
                }
                $('#modalOpenViewer').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');
                break;
        }
    });

    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/administrators', {
        'query': {'jwt': localStorage.getItem("token")},
        'path': '/api/v3/socket.io/',
        'transports': ['websocket']
    });

    socket.on('connect', function() {
        connection_done();
        console.log('Listening users namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });

     startClientVpnSocket(socket);

    socket.on('user_quota', function(data) {
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

    countdown ={}
    socket.on('desktop_data', function(data){
        var data = JSON.parse(data);

        if(data.status =='Started' && 'viewer' in data && 'guest_ip' in data['viewer']){
            if(!('viewer' in table.row('#'+data.id).data()) || !('guest_ip' in table.row('#'+data.id).data())){
                viewerButtonsIP(data['viewer']['guest_ip'])
         }
        }

        if (data.status =='Started' && table.row('#'+data.id).data().status != 'Started') {
            setViewerButtons(data,socket);
        } else {
            //~ if('ephimeral' in data && !countdown[data.id]){
                clearInterval(countdown[data.id])
                countdown[data.id]=null
            //~ }
        }

        dtUpdateInsert(table,data,false);
        setDesktopDetailButtonsStatus(data.id, data.status, data.server);
    });

    socket.on('desktop_delete', function(data){
        var data = JSON.parse(data);
        var row = table.row('#'+data.id).remove().draw();
        new PNotify({
                title: "Desktop deleted",
                text: "Desktop "+data.name+" has been deleted",
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
        });
    });

    socket.on('result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $('.modal').modal('hide');
        }
        if(data.title){
            new PNotify({
                    title: data.title,
                    text: data.text,
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-'+data.icon,
                    opacity: 1,
                    type: data.type
            });
        };
    });

    socket.on('add_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $("#modalAdd")[0].reset();
            $("#modalAddDesktop").modal('hide');
            $("#modalTemplateDesktop #modalTemplateDesktopForm")[0].reset();
            $("#modalTemplateDesktop").modal('hide');            
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
            //setHardwareDomainDefaults_viewer('#hardware-'+data.id,data);
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
});


function actionsDesktopDetail(){
    $('.btn-edit').on('click', function () {
            var pk=$(this).closest("[data-pk]").attr("data-pk");
            $("#modalEdit")[0].reset();
            setHardwareOptions('#modalEditDesktop','hd',pk);
            setHardwareDomainIdDefaults('#modalEditDesktop',pk);
            setMedia_add('#modalEditDesktop #media-block')
            $('#modalEditDesktop').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            $('#modalEdit').parsley();
    });

    $('.btn-template').on('click', function () {
        if($('.quota-templates .perc').text() >=100){
            new PNotify({
                title: "Quota for creating templates full.",
                text: "Can't create another template, quota full.",
                hide: true,
                delay: 3000,
                icon: 'fa fa-alert-sign',
                opacity: 1,
                type: 'error'
            });
        }else{  
            var pk=$(this).closest("[data-pk]").attr("data-pk");
            
            setDefaultsTemplate(pk);

            $('#modalTemplateDesktop').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');

            setAlloweds_add('#modalTemplateDesktop #alloweds-add');          
            $('#modalTemplateDesktopForm').parsley().validate();
        }
    });

    $('#modalTemplateDesktop').on('shown.bs.modal', function () {
            validator.checkAll($('#modalTemplateDesktopForm')[0]);
        });

    $('.btn-delete').on('click', function () {
                var pk=$(this).closest("[data-pk]").attr("data-pk");
                var name=$(this).closest("[data-pk]").attr("data-name");
                new PNotify({
                        title: 'Confirmation Needed',
                            text: "Are you sure you want to delete virtual machine: "+name+"?",
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
                            api.ajax('/api/v3/desktop/' + pk, 'DELETE').done(function() {});
                        }).on('pnotify.cancel', function() {
                }); 
    });

    $('.btn-xml').on('click', function () {
            var pk=$(this).closest("[data-pk]").attr("data-pk");
            $("#modalShowInfoForm")[0].reset();
            $('#modalEditXml').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            $('#modalShowInfoForm #id').val(pk);
            $.ajax({
                type: "GET",
                url:"/isard-admin/admin/domains/xml/" + pk,
                success: function(data)
                {
                    var data = JSON.parse(data);
                    $('#xml').val(data);
                }               
            });
    });

    $('.btn-jumperurl').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        $("#modalJumperurlForm")[0].reset();
        $('#modalJumperurlForm #id').val(pk);
        $('#modalJumperurl').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        // setModalUser()
        // setQuotaTableDefaults('#edit-users-quota','users',pk) 
        api.ajax('/api/v3/desktop/jumperurl/'+pk,'GET',{}).done(function(data) {
            if(data.jumperurl != false){
                $('#jumperurl').show();
                $('.btn-copy-jumperurl').show();
                //NOTE: With this it will fire ifChecked event, and generate new key
                // and we don't want it now as we are just setting de initial state
                // and don't want to reset de key again if already exists!
                //$('#jumperurl-check').iCheck('check');
                $('#jumperurl-check').prop('checked',true).iCheck('update');

                $('#jumperurl').val(location.protocol + '//' + location.host+'/vw/'+data.jumperurl);
            }else{
                $('#jumperurl-check').iCheck('update')[0].unchecked;
                $('#jumperurl').hide();
                $('.btn-copy-jumperurl').hide();
            }
        }); 
    });

    $('.btn-server').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        $("#modalServerForm")[0].reset();
        $('#modalServer').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalServerForm #id').val(pk);
        $.ajax({
            type: "POST",
            url:"/api/v3/admin/table/domains",
            data: JSON.stringify({
                'id': pk,
                'pluck': "server"
            }),
            contentType: 'application/json',
            success: function(data)
            {
                if(data.server == true){
                    $('#modalServerForm #server').iCheck('check').iCheck('update');
                }else{
                    $('#modalServerForm #server').iCheck('unckeck').iCheck('update');
                } 
            }				
        });
    });

    $("#modalServer #send").off('click').on('click', function(e){
        data=$('#modalServerForm').serializeObject();
        let pk=$('#modalServerForm #id').val()
        let server=$('#modalServerForm #server').prop('checked')
        $.ajax({
            type: "PUT",
            url: "/api/v3/domain/" + pk,
            data: JSON.stringify({
                'id': pk,
                'server': server
            }),
            contentType: "application/json",
            success: function(data)
            {
                $('form').each(function() { this.reset() });
                $('.modal').modal('hide');
                new PNotify({
                    title: "Updated desktop as server",
                    text: "Server desktop has been updated...",
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-success',
                    opacity: 1,
                    type: "success"
                });
            },
            error: function(data){
                new PNotify({
                    title: "ERROR",
                    text: "Can't update desktop as server",
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 15000,
                    opacity: 1
                });
            }
        });
        $("#modalServer").modal('hide');
    });

    
        $('#jumperurl-check').unbind('ifChecked').on('ifChecked', function(event){
            if($('#jumperurl').val()==''){
                pk=$('#modalJumperurlForm #id').val();
                $.ajax({
                    url: '/api/v3/desktop/jumperurl_reset/' + pk, 
                    type: 'PUT',
                    contentType: "application/json",
                    data: JSON.stringify({"disabled" : false}),
                    success: function(data) {
                        $('#jumperurl').val(location.protocol + '//' + location.host+'/vw/'+data);
                    }
                })         
                $('#jumperurl').show();
                $('.btn-copy-jumperurl').show();
            }
          });   
        $('#jumperurl-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
            pk=$('#modalJumperurlForm #id').val();
            new PNotify({
                title: 'Confirmation Needed',
                    text: "Are you sure you want to delete direct viewer access url?",
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
                    pk=$('#modalJumperurlForm #id').val();
                    $.ajax({
                        url: '/api/v3/desktop/jumperurl_reset/' + pk, 
                        type: 'PUT',
                        contentType: "application/json",
                        data: JSON.stringify({"disabled" : true}),
                        success: function(data) {
                            $('#jumperurl').val('');
                        }
                    }) 
                    $('#jumperurl').hide();
                    $('.btn-copy-jumperurl').hide();
                }).on('pnotify.cancel', function() {
                    $('#jumperurl-check').iCheck('check');
                    $('#jumperurl').show();
                    $('.btn-copy-jumperurl').show();
                });
            }); 

        $('.btn-copy-jumperurl').on('click', function () {
            $('#jumperurl').prop('disabled',false).select().prop('disabled',true);
            document.execCommand("copy");
        });

}
        
//~ RENDER DATATABLE    
function addDesktopDetailPannel ( d ) {
        $newPanel = $template.clone();
        $newPanel.find('#derivates-d\\.id').remove();
        $newPanel.find('.btn-forcedhyp').remove();
        $newPanel.find('.btn-xml').remove();
        $newPanel.html(function(i, oldHtml){
            return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name);
        });
        return $newPanel
}

function setDesktopDetailButtonsStatus(id,status,server){
    if(status=='Stopped'){
        $('#actions-'+id+' *[class^="btn"]').prop('disabled', false);
    }else{
        $('#actions-'+id+' *[class^="btn"]').prop('disabled', true);
        $('#actions-'+id+' .btn-jumperurl').prop('disabled', false);
    }
    if(status=='Failed'){
        $('#actions-'+id+' .btn-edit').prop('disabled', false);
        $('#actions-'+id+' .btn-delete').prop('disabled', false);
    }
    $('#actions-'+id+' .btn-server').prop('disabled', false);
    if (server) {
        $('#actions-'+id+' .btn-template').prop('disabled', true);
    }
}
        
function icon(name){
       if(name=='windows' || name=='linux'){
           return "<i class='fa fa-"+name+" fa-2x '></i>";
        }else{
            return "<span class='fl-"+name+" fa-2x'></span>";
        }       
}


function renderDisplay(data){
        if(['Started', 'Shutting-down', 'Stopping'].includes(data.status)){
            return ' <div class="display"> \
                    <button type="button" id="btn-display" class="btn btn-pill-right btn-success btn-xs"> \
                    <i class="fa fa-desktop"></i> Show</button></div>';
        }
        return ''
}

function renderName(data){
        return '<div class="block_content" > \
                <h4 class="title" style="margin-bottom: 0.1rem; margin-top: 0px;"> \
                '+data.name+' \
                </h4> \
                <p class="excerpt" >'+data.description+'</p> \
                </div>'
}

function renderStatus(data,table){
    if(data.status =='Started' && 'ephimeral' in data && !countdown[data.id]){
            countdown[data.id]=setInterval(function(){
                if(data.finish < moment().unix()){clearInterval(countdown[data.id]);}
                data.description="<b style='color:red'>REMAINIG STARTED DESKTOP TIME: "+moment.unix(data.ephimeral.finish).diff(moment(), "seconds")+' seconds</b>'
                dtUpdateInsert(table,data,false);
                },1000);
    }
    return data.status;
}

function renderAction(data){
    status=data.status;
    if(status=='Stopped' || status=='Failed'){
        return '<button type="button" id="btn-play" class="btn btn-pill-right btn-success btn-xs"><i class="fa fa-play"></i> Start</button>';
    }
    if(status=='Started'){
        return '<button type="button" id="btn-stop" class="btn btn-pill-left btn-danger btn-xs"><i class="fa fa-stop"></i> Stop</button>';
    }
    if(status=='Shutting-down'){
        return '<button type="button" id="btn-stop" class="btn btn-pill-left btn-danger btn-xs"><i class="fa fa-spinner fa-pulse fa-fw"></i> Force stop</button>';
    } 
    if(status=='Crashed'){
        return '<div class="Change"> <i class="fa fa-thumbs-o-down fa-2x"></i> </div>';
    } 
    if(status=='Disabled'){
            return '<i class="fa fa-times fa-2x"></i>';
    }
    return '<i class="fa fa-spinner fa-pulse fa-2x fa-fw"></i>';
}

function renderMedia(data){
    html=''
    if('isos' in data.create_dict.hardware){
        $.each(data.create_dict.hardware.isos,function(key, value){
            html+='<i class="fa fa-circle-o fa-2x" title="ISO cd file"></i> ';
            //html+='<i class="fa fa-circle-o fa-2x" title="'+value.name+'"></i> ';
        });
    }
    if('floppies' in data.create_dict.hardware){
        $.each(data.create_dict.hardware.floppies,function(key, value){
            html+='<i class="fa fa-floppy-o fa-2x" title="Floppy disk file"></i> ';
        });
    }
    if('storage' in data.create_dict.hardware){
        $.each(data.create_dict.hardware.storage,function(key, value){
            html+='<i class="fa fa-hdd-o fa-2x" title="Storage disk file"></i> ';
        });
    }    
    return html;
}

function renderHotplugMedia(data){
    html='<button class="btn btn-xs btn-hotplug" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button> '
    if('hotplug' in data){
        $.each(data.hotplug,function(key, value){
            if(value.kind=='iso'){
                html+='<i class="fa fa-circle-o fa-2x" title="'+value.id+'"></i> ';
            }
            if(value.kind=='fd'){
                if(value.status=='Plugging'){
                    html+='<i class="fa fa-floppy-o fa-2x blink" title="'+value.name+'" style="color:#ff9933"></i> ';
                }else{
                    html+='<i class="fa fa-floppy-o fa-2x" title="'+value.name+'" style="color:#0c3300"></i> ';
                }
            }                
        });
    }
    return html;
}

function setDefaultsTemplate(id) {
    $.ajax({
        type: "GET",
        url:"/api/v3/domain/info/" + id,
        success: function(data)
        {
            $('.template-id').val(id);
            $('.template-id').attr('data-pk', id);
            $('.template-name').val('Template '+data.name);
            $('.template-description').val(data.description);
            $('#modalTemplateDesktop #enabled').iCheck('check')
        }               
    });
}


function modal_add_desktop_datatables(){
    modal_add_desktops.destroy()
    $('#modalAddDesktop #template').val('');
    $('#modalAddDesktop #datatables-error-status').empty()
    $('#modal_add_desktops thead th').each( function () {
    } );
    

    modal_add_desktops = $('#modal_add_desktops').DataTable({
            "ajax": {
                "url": "/api/v3/user/templates/allowed/all",
                "dataSrc": ""
            },
            "scrollY":        "350px",
            "scrollCollapse": true,
            "paging":         true,
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
                { "data": "description"},
                { "data": "group_name"},
                { "data": "user_name"}
                ],
             "order": [[0, 'asc']], 
             "pageLength": 10,   
        "columnDefs": [     

                            ]
    } );  
}

function initalize_modal_all_desktops_events(){
   $('#modal_add_desktops tbody').on( 'click', 'tr', function () {
        rdata=modal_add_desktops.row(this).data()
        if ( $(this).hasClass('selected') ) {
            $(this).removeClass('selected');
            $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
            $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
            
            $('#modalAddDesktop #template').val('');
            $('#modalAddDesktop #btn-hardware').hide();
            $('#modalAddDesktop #hardware-block').hide();
        }
        else {
            modal_add_desktops.$('tr.selected').removeClass('selected');
            $(this).addClass('selected');
            $('#modal_add_desktops').closest('.x_panel').removeClass('datatables-error');
            $('#modalAddDesktop #datatables-error-status').empty().html('<b style="color:DarkSeaGreen">Template selected: '+rdata['name']+'</b>').removeClass('my-error');
            $('#modalAddDesktop #template').val(rdata['id']);
            //if(user['role']!='user'){
                $('#modalAddDesktop #btn-hardware').show();
                setHardwareDomainIdDefaults('#modalAddDesktop',rdata['id'])
            //}
        }
    } );    

    $("#modalTemplateDesktop #send").on('click', function(e){
            var form = $('#modalTemplateDesktopForm');
            form.parsley().validate();
            if (form.parsley().isValid()){
                desktop_id=$('#modalTemplateDesktopForm #id').val();
                if (desktop_id !=''){
                    data=$('#modalTemplateDesktopForm').serializeObject();
                    data=replaceAlloweds_arrays('#modalTemplateDesktopForm #alloweds-add',data)
                    data['enabled']=$('#modalTemplateDesktop #enabled').prop('checked');

                    name=data["name"]
                    allowed=data["allowed"]
                    description=data["description"]
                    enabled=data["enabled"]

                    var notice = new PNotify({
                        text: 'Creating desktop...',
                        hide: false,
                        opacity: 1,
                        icon: 'fa fa-spinner fa-pulse'
                    })
                    $('form').each(function() {
                        this.reset()
                    })
                    $('.modal').modal('hide');
                    $.ajax({
                        type: "POST",
                        url:"/api/v3/template",
                        data: JSON.stringify({name, desktop_id, allowed, description, enabled}),
                        contentType: "application/json",
                        error: function(data) {
                            notice.update({
                                title: 'ERROR',
                                text: 'Cannot create template ' + name,
                                type: 'error',
                                hide: true,
                                icon: 'fa fa-warning',
                                delay: 5000,
                                opacity: 1
                            })
                        },
                        success: function(data) {
                            notice.update({
                                title: 'New template',
                                text: 'Template '+ name + ' created successfully',
                                hide: true,
                                delay: 2000,
                                icon: 'fa fa-' + data.icon,
                                opacity: 1,
                                type: 'success'
                            })
                        }
                    });
    
                }else{
                    $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                }
            }
        });

}

$("#modalEditDesktop #send").on('click', function(e){
    var form = $('#modalEdit');
    form.parsley().validate();
    if (form.parsley().isValid()){
        data=$('#modalEdit').serializeObject();
        if( ("viewers-file_rdpgw" in data || "viewers-file_rdpvpn" in data || "viewers-browser_rdp" in data) && ! data["hardware-interfaces"].includes("wireguard") ){
            new PNotify({
                title: "Incompatible options",
                    text: "RDP viewers need the wireguard network. Please add wireguard network to this desktop or remove RDP viewers.",
                    hide: true,
                    delay: 6000,
                    icon: 'fa fa-alert-sign',
                    opacity: 1,
                    type: 'error'
                });
            return
        }
        data['reservables-vgpus'] = [data['reservables-vgpus']]
        data=parse_desktop(JSON.unflatten(parseViewersOptions(data)));
        var notice = new PNotify({
            text: 'Updating selected item...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        $.ajax({
            type: 'PUT',
            url: '/api/v3/domain/'+data["id"],
            data: JSON.stringify(data),
            contentType: 'application/json',
            error: function(data) {
                notice.update({
                    title: 'ERROR',
                    text: 'Something went wrong when updating',
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            },
            success: function(data) {
                $("#modalEdit")[0].reset();
                $("#modalEditDesktop").modal('hide');
                table.ajax.reload()
                notice.update({
                    title: 'Updated',
                    text: 'Item updated successfully',
                    hide: true,
                    delay: 2000,
                    icon: 'fa fa-' + data.icon,
                    opacity: 1,
                    type: 'success'
                })
            }
        })
    }
});

function parse_desktop(data){
    return {
        "id": data["id"],
        "name": data["name"],
        "description": data["description"],
        "guest_properties": data["guest_properties"],
        "hardware": {
            ...("vcpus" in data["hardware"]) && {"vcpus": parseInt(data["hardware"]["vcpus"])},
            ...("memory" in data["hardware"]) && {"memory": parseFloat(data["hardware"]["memory"])},
            ...("videos" in data["hardware"]) && {"videos": [data["hardware"]["videos"]]},
            ...("boot_order" in data["hardware"]) && {"boot_order": [data["hardware"]["boot_order"]]},
            ...("interfaces" in data["hardware"]) && {"interfaces": data["hardware"]["interfaces"]},
            ...("disk_bus" in data["hardware"]) && {"disk_bus": data["hardware"]["disk_bus"]},
            ...("disk_size" in data["hardware"]) && {"disk_size": parseInt(data["hardware"]["disk_size"])},
            ...( true) && {"isos":[]},
            ...("m" in data && "isos" in data["m"]) && {"isos": setMediaIds(data["m"]["isos"])},
            ...( true) && {"floppies":[]},
            ...("m" in data && "floppies" in data["m"]) && {"floppies": setMediaIds(data["m"]["floppies"])},
            "reservables": {
                ...( true ) && {"vgpus":data["reservables"]["vgpus"]},
                ...( data["reservables"]["vgpus"].includes(undefined) || data["reservables"]["vgpus"] == null || data["reservables"]["vgpus"].includes("None") ) &&  {"vgpus": null},
            },
          },
        }
}
