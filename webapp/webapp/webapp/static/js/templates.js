/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var $template='';
var table='';
$(document).ready(function() {
    $('.admin-status').hide()
    $template = $(".template-detail");
    table = $('#templates').DataTable({
            "ajax": {
                "url": "/api/v3/user/webapp_templates",
                "dataSrc": ""
            },
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
                "defaultContent": '<button id="btn-detail" class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
                },
                { "data": "icon", "width": "10px" },
                { "data": "name"},
                { "data": "status"},
                {
                    "data": 'enabled',
                    "className": 'text-center',
                    "data": null,
                    "orderable": false,
                    "defaultContent": '<input type="checkbox" class="form-check-input" checked></input>'
                },
                { "data": null, 'defaultContent': ''},
                { "data": "description", "visible": false},
                
                ],
             "order": [[2, 'asc']],
             "columnDefs": [ {
                            "targets": 1,
                            "render": function ( data, type, full, meta ) {
                                url = location.protocol+'//' + document.domain + ':' + location.port + full.image.url
                                return "<img src='"+url+"' width='50px'>"
                            }},
                            {
                            "targets": 2,
                            "render": function ( data, type, full, meta ) {
                              return renderName(full);
                            }},
                            {
                            "targets": 3,
                            "render": function ( data, type, full, meta ) {
                              return renderStatus(full);
                            }},
                            {
                            "targets": 4,
                            "render": function ( data, type, full, meta ) {
                                if( full.enabled ){
                                    return '<input id="chk-enabled" type="checkbox" class="form-check-input" checked></input>'
                                }else{
                                    return '<input id="chk-enabled" type="checkbox" class="form-check-input"></input>'
                                }
                            }},
                            {
                                "targets": 5,
                                "render": function ( data, type, full, meta ) {
                                    if(full.status == 'Stopped' || full.status == 'Stopped'){
                                        return '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button>'
                                    } 
                                    return full.status; 
                                }},
                            ]
        } );
    
    $('#templates').find('tbody').on('click', 'td.details-control', function () {
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
            row.child( formatPanel(row.data()) ).show();
            tr.addClass('shown');
            setHardwareDomainDefaults_viewer('#hardware-'+row.data().id,row.data());
	    //~ setDomainGenealogy(row.data().id)
            setAlloweds_viewer('#alloweds-'+row.data().id,row.data().id);
            actionsTmplDetail();
            
        }
    });

    $('#templates').find(' tbody').on( 'click', 'input', function () {
        var pk=table.row( $(this).parents('tr') ).id();
        switch($(this).attr('id')){
            case 'chk-enabled':
                if ($(this).is(":checked")){
                    enabled=true
                }else{
                    enabled=false
                }
                api.ajax('/api/v3/template/update',
                        'PUT',
                        {'id':pk,
                        'enabled':enabled})
                .fail(function(jqXHR) {
                    new PNotify({
                        title: "Template enable/disable",
                            text: "Could not update!",
                            hide: true,
                            delay: 3000,
                            icon: 'fa fa-alert-sign',
                            opacity: 1,
                            type: 'error'
                        });
                        table.ajax.reload()
                }); 
            break;
        }
    })

    $('#templates').find(' tbody').on( 'click', 'button', function () {
        var data = table.row( $(this).parents('tr') ).data();

        switch($(this).attr('id')){
            //~ case 'btn-detail':
                //~ var tr = $(this).closest('tr');
                //~ var row = table.row( tr );
                //~ if ( row.child.isShown() ) {
                    //~ // This row is already open - close it
                    //~ row.child.hide();
                    //~ row.child.remove();
                    //~ tr.removeClass('shown');
                //~ }
                //~ else {
                    //~ // Open this row
                    //~ row.child( formatPanel(row.data()) ).show();
                    //~ tr.addClass('shown');
                    //~ setHardwareDomainDefaults_viewer('#hardware-'+row.data().id,row.data().id);
                    //~ setHardwareGraph();
                    //~ setAlloweds_viewer('#alloweds-'+row.data().id,row.data().id);
                    //~ actionsTmplDetail();
                    
                //~ }
                //~ break;
             case 'btn-alloweds':
                    modalAllowedsFormShow('domains',data)
             break;                
        };
    });   

   
    //~ Delete confirm modal
    $('#confirm-modal > .modal-dialog > .modal-content > .modal-footer > .btn-primary').click(function() {
        //~ console.log('id:'+$('#confirm-modal').data('id')+' - action: delete');
        // Needs some work
        });
        
    $('#confirm-modal').on('show.bs.modal', function (event) {
      var button = $(event.relatedTarget);
      var id = button.data('id'); // Extract data-* attributes
      var name = button.data('name');
      var modal = $(this);
      modal.data('id',id);
      modal.find('.modal-title').text('Do you really want to remove "' + name + '" desktop?');
      modal.find('.modal-body').text('The desktop will be permanently deleted (unrecoverable)')
    });

    // SocketIO
        socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/administrators', {
        'query': {'jwt': localStorage.getItem("token")},
        'path': '/api/v3/socket.io/',
        'transports': ['websocket']
    });

    socket.on('connect', function() {
        connection_done();
        console.log('Listening user namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
    socket.on('user_quota', function(data) {
        console.log('Quota update')
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

    socket.on('template_data', function(data){
        //~ console.log('update')
        var data = JSON.parse(data);
        dtUpdateInsert(table,data,false);
        //~ setDesktopDetailButtonsStatus(data.id, data.status);

        
        //~ var data = JSON.parse(data);
        //~ var row = table.row('#'+data.id); 
        //~ table.row(row).data(data);
        //~ setDesktopDetailButtonsStatus(data.id, data.status);
    });

    socket.on('template_add', function(data){
        //~ console.log('add')
        var data = JSON.parse(data);
        if($("#" + data.id).length == 0) {
          //it doesn't exist
          table.row.add(data).draw();
        }else{
          //if already exists do an update (ie. connection lost and reconnect)
          var row = table.row('#'+data.id); 
          table.row(row).data(data);            
        }
    });
    
    socket.on('template_delete', function(data){
        //~ console.log('delete')
        var data = JSON.parse(data);
        var row = table.row('#'+data.id).remove().draw();
        new PNotify({
                title: "Desktop deleted",
                text: "Desktop "+data.name+" has been deleted",
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'info'
        });
    });

//~ // SERVER SENT EVENTS Stream
    //~ if (!!window.EventSource) {
      //~ var desktops_source = new EventSource('/stream/isard-admin/desktops');
      //~ console.log('on event');
    //~ } else {
      //~ // Result to xhr polling :(
    //~ }

    //~ window.onbeforeunload = function(){
      //~ desktops_source.close();
    //~ };

    //~ desktops_source.addEventListener('New', function(e) {
      //~ var data = JSON.parse(e.data);
        //~ if($("#" + data.id).length == 0) {
          //~ //it doesn't exist
          //~ table.row.add( formatTmplDetails(data)).draw();
        //~ }else{
          //~ //if already exists do an update (ie. connection lost and reconnect)
            //~ var row = table.row('#'+data.id); 
            //~ table.row(row).data(formatTmplDetails(data));           
        //~ }
      
        //~ if(data.status=='Stopped'){
            //~ // Should disable details buttons
        //~ }else{
            //~ // And enable it again
        //~ }
    //~ }, false);

    //~ desktops_source.addEventListener('Status', function(e) {
      //~ var data = JSON.parse(e.data);
      //~ var row = table.row('#'+data.id); 
      //~ table.row(row).data(formatTmplDetails(data));
    //~ }, false);

    //~ desktops_source.addEventListener('Deleted', function(e) {
      //~ var data = JSON.parse(e.data);
      //~ // var row =
        //~ table.row('#'+data.id).remove().draw();
    //~ }, false);


});   // document ready

function formatTmplDetails(data){
        var row=$('*[data-pk="'+data.id+'"]');
        if(data.status=='Stopped'){
            row.find('.btn-delete').prop('disabled', false);
        }else{
            row.find('.btn-delete').prop('disabled', true);
        }
        return data;
}

function formatPanel ( d ) {
        $newPanel = $template.clone();
        $newPanel.html(function(i, oldHtml){
            return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.kind/g, d.kind);
        });
        if(d.status=='Stopped'){
            $newPanel.find('.btn-actions').prop('disabled', false);
        }else{
            $newPanel.find('.btn-actions').prop('disabled', true);
        }
        return $newPanel
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
                    text: data.responseJSON.description,
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

function actionsTmplDetail(){
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
}

function icon(name){
    if(name=='windows' || name=='linux'){
        return "<span ><i class='fa fa-"+name+" fa-2x'></i></span>";
    }else{
        return "<span class='fl-"+name+" fa-2x'></span>";
    }
}

function renderName(data){
    return '<div class="block_content" > \
            <h4 class="title" style="margin-bottom: 0.1rem; margin-top: 0px;"> \
            <a>'+data.name+'</a> \
            </h4> \
            <p class="excerpt" >'+data.description+'</p> \
            </div>'
}

function renderStatus(data){
    return data.status
}

function renderPending(data){
    status=data.status;
    if(status=='Stopped'){
        return 'None';
    }
    return '<div class="Change"> <i class="fa fa-spinner fa-pulse fa-2x fa-fw"></i><span class="sr-only">Working...</span></i> </div>';
}
