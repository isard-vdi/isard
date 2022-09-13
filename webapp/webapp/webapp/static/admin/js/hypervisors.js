/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$hypervisor_template = $(".hyper-detail");

$(document).ready(function() {
    $('.admin-status').show()

    $('.btn-new-hyper').on('click', function () {
            $('#modalAddHyper').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            $("#modalAddHyper #hypervisors_pools_dropdown").find('option').remove();

            $.ajax({
                url: "/admin/table/hypervisors_pools",
                type: "POST",
                data: JSON.stringify({'order_by':'name'}),
                contentType: "application/json",
                success: function(pools)
                {
                    $.each(pools,function(key, value) 
                    {
                        $("#modalAddHyper #hypervisors_pools_dropdown").append('<option value=' + value.id + '>' + value.name + '</option>');
                    });
                },
                error: function (jqXHR, exception) {
                    processError(jqXHR,form)
                }
            });
            
            $('#modalAddHyper #modalAdd #hostname').val(window.location.hostname)
            $('#modalAddHyper #modalAdd #user').val('root')
            $('#modalAddHyper #modalAdd #port').val(2022)
            $('#modalAddHyper #modalAdd #capabilities-disk_operations').iCheck('check')
            $('#modalAddHyper .capabilities_hypervisor').on('ifChecked', function(event){
                $('#viewer_fields').show()
                    $('#modalAddHyper #viewer-static').val($('#modalAddHyper #modalAdd #hostname').val());
                    $('#modalAddHyper #viewer-proxy_video').val($('#modalAddHyper #modalAdd #hostname').val());
                    $('#modalAddHyper #viewer-proxy_hyper_host').val('isard-hypervisor');
                    $('#modalAddHyper #viewer-hyper_vpn_host').val('isard-hypervisor');
            });

            $('#modalAddHyper .capabilities_hypervisor').on('ifUnchecked', function(event){
                $('#modalAddHyper #viewer_fields').hide()
                    $('#modalAddHyper #modalAddHyper #viewer-static').val('');
                    $('#modalAddHyper #modalAddHyper #viewer-proxy_video').val('');
                    $('#modalAddHyper #modalAddHyper #viewer-proxy_hyper_host').val(0);
            });

    });

    $("#modalAddHyper #send").on('click', function(e){

        var form = new FormData()
        form.append('hyper_id', $('#modalAddHyper #modalAdd #id').val())
        form.append('description', $('#modalAddHyper #modalAdd textarea[name="description"]').val())
        form.append('hostname', $('#modalAddHyper #modalAdd #hostname').val())
        form.append('user', $('#modalAddHyper #modalAdd #user').val())
        form.append('port', $('#modalAddHyper #modalAdd #port').val())
        form.append('cap_hyper', $('#modalAddHyper #modalAdd #capabilities-hypervisor').prop('checked'))
        form.append('cap_disk', $('#modalAddHyper #modalAdd #capabilities-disk_operations').prop('checked'))
        form.append('isard_static_url', $('#modalAddHyper #modalAdd #viewer-static').val())
        form.append('isard_video_url', $('#modalAddHyper #modalAdd #viewer-proxy_video').val())
        form.append('spice_port', $('#modalAddHyper #modalAdd #viewer-spice_ext_port').val())
        form.append('browser_port', $('#modalAddHyper #modalAdd #viewer-html5_ext_port').val())
        form.append('isard_proxy_hyper_url', $('#modalAddHyper #modalAdd #viewer-proxy_hyper_host').val())
        form.append('isard_hyper_vpn_host', $('#modalAddHyper #modalAdd #viewer-hyper_vpn_host').val())
        form.append('enabled', false) 
        

        $('#modalAddHyper #modalAdd').parsley().validate();
        if ($('#modalAddHyper #modalAdd').parsley().isValid()) {
            $.ajax({
                type: "POST",
                url:"/api/v3/hypervisor",
                data: form,
                processData: false,
                contentType: false,
                success: function(data)
                {
                    $('form').each(function() { this.reset() });
                    $('.modal').modal('hide');
                },
                error: function (xhr, ajaxOptions, thrownError) {
                    if (xhr.status == 404) {
                        new PNotify({
                            title: "Cannot connect to hypervisor",
                            text: "Can't create the hypervisor, it's not reachable.",
                            hide: true,
                            delay: 3000,
                            icon: 'fa fa-warning',
                            opacity: 1,
                            type: 'error'
                        });
                    }
                }
            });
        }
    });

    //   function timestamp() { return (new Date).getTime() / 1000; }
    //   chart={}

    renderBoolean = (enabled) => {
        if (enabled) {
            return '<i class="fa fa-circle" aria-hidden="true" style="color:green"></i>'
        } else {
            return '<i class="fa fa-circle" aria-hidden="true" style="color:darkgray"></i>'
        }
    }

    table = $('#hypervisors').DataTable( {
        "ajax": {
            "url": "/admin/table/hypervisors",
            "data": function(d){return JSON.stringify({'order_by':'id'})},
            "contentType": "application/json",
            "type": 'POST'
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
            { "data": "enabled", "width": "10px" },
            { "data": "status", "width": "10px" },
            { "data": "id" , "width": "10px" },
            { "data": "hostname" , "width": "100px" },
            { "data": "vpn.wireguard.connected" , "width": "10px", "defaultContent": 'NaN' },
            { "data": "viewer.static" , "width": "10px" },
            { "data": "viewer.proxy_video" , "width": "10px" },
            { "data": "viewer.proxy_hyper_host" , "width": "10px" },
            { "data": "info.qemu_version" , "width": "10px", "defaultContent": 'NaN'},
            { "data": "info.libvirt_version" , "width": "10px", "defaultContent": 'NaN' },
            { "data": "info.virtualization_capabilities" , "width": "10px", "defaultContent": 'NaN' },
            { "data": "gpus" , "width": "10px", "defaultContent": 'NaN' },
            { "data": "info.memory_in_MB" , "width": "10px", "defaultContent": 'NaN' },
            { "data": "info.virtualization_capabilities" , "width": "10px", "defaultContent": 'NaN' },            
            { "data": "capabilities.disk_operations" , "width": "10px" },
            { "data": "capabilities.hypervisor" , "width": "10px" },
            { "data": "only_forced" , "width": "10px" },
            { "data": "status_time" , "width": "10px" }],
            
          /*   { "data": "started_domains", "width": "10px", "defaultContent": 0}, */
          /*   { "data": "hypervisors_pools", "width": "10px" }, */
            
             "order": [[2, 'asc']],
             "columnDefs": [ {
                            "targets": 1,
                            "render": function ( data, type, full, meta ) {
                              return renderEnabled(full);
                            }},
                            {
                            "targets": 2,
                            "render": function ( data, type, full, meta ) {
                              return renderStatus(full);
                            }},
                            {
                            "targets": 5,
                            "render": renderBoolean
                            },
                            {
                            "targets": 7,
                            "render": function ( data, type, full, meta ) {
                                return full.viewer.proxy_video + ' ('+full.viewer.spice_ext_port + ',' + full.viewer.html5_ext_port + ')';
                            }},
                            {
                            "targets": 13,
                            "render": function ( data, type, full, meta ) {
                                return Math.round(data / 1024 * 10) / 10 + 'GB';
                            }},
                            {
                            "targets": 14,
                            "render": function ( data, type, full, meta ) {
                                if (full.info) {
                                    return full.info.cpu_cores*full.info.threads_x_core;
                                }
                            }},
                            {
                            "targets": 15,
                            "render": renderBoolean
                            },
                            {
                            "targets": 16,
                            "render": renderBoolean
                            },
                            {
                            "targets": 17,
                            "render": renderBoolean
                            },
                            {
                            "targets": 18,
                            "render": function ( data, type, full, meta ) {
                              return moment.unix(full.status_time).fromNow();
                            }}
             ],
    } );

    $('#hypervisors').find('tbody').on('click', 'td.details-control', function () {
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
             //~ if ( table.row( '.shown' ).length ) {
                      //~ $('.details-control', table.row( '.shown' ).node()).click();
              //~ }
            // Open this row
            row.child( formatHypervisorPanel(row.data()) ).show();
            tr.addClass('shown');
            $('#status-detail-'+row.data().id).html(row.data().detail);
            tableHypervisorDomains(row.data().id);
            setHypervisorDetailButtonsStatus(row.data().id,row.data().status)
            actionsHyperDetail();
        }
    } );


        
    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/administrators', {
        'query': {'jwt': localStorage.getItem("token")},
        'path': '/api/v3/socket.io/',
        'transports': ['websocket']
    });
     
    socket.on('connect', function() {
        connection_done();
        console.log('Listening admins namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
    socket.on('user_quota', function(data) {
        console.log('Quota update')
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

    socket.on('hyper_data', function(data){
        //~ console.log('hyper_data')
        //~ console.log(data)
        var data = JSON.parse(data);
        new_hyper=dtUpdateInsert(table,data,false);
        if(new_hyper){tablepools.draw(false);}
        setHypervisorDetailButtonsStatus(data.id,data.status)
        //~ if($("#" + data.id).length == 0) {
          //~ //it doesn't exist
          //~ table.row.add(data); //.draw();
          //~ tablepools.draw(false(
        //~ }else{
          //~ //if already exists do an update (ie. connection lost and reconnect)
          //~ var row = table.row('#'+data.id); 
          //~ data.started_domains = row.data().started_domains
          //~ table.row(row).data(data).invalidate();           
        //~ }
        //~ table.draw(false);
    });

    socket.on('hyper_status', function(data){
        //~ console.log('status')
        var data = JSON.parse(data);
        table.row('#'+data.hyp_id).data().started_domains=data.domains
        table.row('#'+data.hyp_id).invalidate().draw();
        // chart[data.hyp_id].push([
        // //~ chart.push([
        //   { time: timestamp(), y: data['cpu_percent-used']},
        //   { time: timestamp(), y: data['load-percent_free']}
        // ]);
    });
        
    socket.on('hyper_deleted', function(data){
        var data = JSON.parse(data);
        //~ console.log('hyper deleted:'+data.id)
        //~ var row = table.row('#'+data.id).remove().draw();
         
        new PNotify({
                title: "Hypervisor deleted",
                text: "Hypervisor "+data+" has been deleted",
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
        });
        table.ajax.reload()
        tablepools.ajax.reload()
    });

    socket.on('add_form_result', function (data) {
        //~ console.log('received result')
        var data = JSON.parse(data);
        if(data.result){
            $("#modalAddHyper #modalAdd")[0].reset();
            $("#modalAddHyper").modal('hide');
            $("#modalEditHyper #modalEdit")[0].reset();
            $("#modalEditHyper").modal('hide');            
            //~ $('body').removeClass('modal-open');
            //~ $('.modal-backdrop').remove();
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
        table.ajax.reload()
        tablepools.ajax.reload()        
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

});// document ready

function renderName(data){
        return '<div class="block_content" > \
                <h4 class="title" style="height: 4px; margin-top: 0px;"> \
                <a>'+data.hostname+'</a> \
                </h4> \
                <p class="excerpt" >'+data.description+'</p> \
                </div>';
}


function formatHypervisorData(data){
        return data;
}
    
function formatHypervisorPanel( d ) {
        $newPanel = $hypervisor_template.clone();
        $newPanel.html(function(i, oldHtml){
            return oldHtml.replace(/d.id/g, d.id);
        });
        return $newPanel
}

function setHypervisorDetailButtonsStatus(id,status){
          if(status=='Online'){
              $('#actions-domains-'+id+' *[class^="btn"]').prop('disabled', false);
            //   $('#actions-extra-'+id+' *[class^="btn"]').prop('disabled', false);
              //~ $('#actions-enable-'+id+' *[class^="btn"]').prop('disabled', false);
              
          }else{
              $('#actions-domains-'+id+' *[class^="btn"]').prop('disabled', true);
            //   $('#actions-extra-'+id+' *[class^="btn"]').prop('disabled', true);
          } 


          if(status=='Offline' || status=='Error'){
              $('#actions-delete-'+id+' .btn-delete').prop('disabled', false);
              $('#actions-delete-'+id+' .btn-edit').prop('disabled', false);
              
          }else{
              $('#actions-delete-'+id+' .btn-delete').prop('disabled', true);
              $('#actions-delete-'+id+' .btn-edit').prop('disabled', true);
          } 
          
          //~ if(status=='Online'){
              //~ $('#actions-domains-'+id+' *[class^="btn"]').prop('disabled', false);
              //~ $('#actions-enable-'+id+' *[class^="btn"]').prop('disabled', false);
              
          //~ }else{
              //~ $('#actions-domains-'+id+' *[class^="btn"]').prop('disabled', true);
          //~ } 
          
          
          
    
          if(status=='Deleting'){
                $('#actions-enable-'+id+' *[class^="btn"]').prop('disabled', true);
                $('#delete_btn_text').html('Force delete')
                $('#actions-delete-'+id+' .btn-delete').prop('disabled', false);
          }else{
              $('#actions-enable-'+id+' *[class^="btn"]').prop('disabled', false);
                //~ $('#delete_btn_text').html('Delete')
                //~ $('#actions-'+id+' *[class^="btn"]').prop('disabled', false);
          }
          

}

function actionsHyperDetail(){
        $('.btn-enable').off('click').on('click', function () {
                var closest=$(this).closest("div");
                var pk=closest.attr("data-pk");
                var data = table.row("#"+pk).data();
                new PNotify({
                        title: 'Confirmation Needed',
                            text: "Are you sure you want to enable/disable: "+pk+"?",
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
                            api.ajax('/admin/table/update/hypervisors', 'PUT',{'id':pk, 'enabled':!data.enabled}).done(function(hyp) {});
                        }).on('pnotify.cancel', function() {
                    }); 
                });

        $('.btn-delete').on('click', function () {
                var pk=$(this).closest("div").attr("data-pk");
                new PNotify({
                        title: 'Confirmation Needed',
                            text: "Are you sure you want to delete hypervisor: "+pk+"?",
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
                            api.ajax('/api/v3/hypervisor/' + pk, 'DELETE').done(function(hyp) {});
                        }).on('pnotify.cancel', function() {
                }); 
            });  

        $('.btn-domstop').on('click', function () {
                var pk=$(this).closest("div").attr("data-pk");
                new PNotify({
                        title: 'Confirmation Needed',
                            text: "Are you sure you want to FORCE stop all domains in hypervisor: "+pk+"?",
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
                            api.ajax('/api/v3/hypervisor/stop/' + pk, 'PUT').done(function(hyp) {});
                        }).on('pnotify.cancel', function() {
                }); 
            }); 

    $('.btn-webstorage').on('click', function () {
        var pk=$(this).closest("div").attr("data-pk");
        var data = table.row("#"+pk ).data();
        storage_url='https://'+data.viewer.proxy_video+':'+data.viewer.html5_ext_port+'/storage'
        window.open(storage_url, '_blank');
    });

    $('.btn-edit').on('click', function () {
                var pk=$(this).closest("div").attr("data-pk");
            $("#modalEdit")[0].reset();
            $("#modalEditHyper #hypervisors_pools_dropdown").find('option').remove();
            
            $('#modalEditHyper').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');

            api.ajax('/admin/table/hypervisors','POST',{'id':pk}).done(function(hyp) {
                $('#modalEditHyper #modalEdit #id').val(pk);
                $('#modalEditHyper #modalEdit #fake_id').val(pk);
                $('#modalEditHyper #modalEdit #description').val(hyp.description);
                $('#modalEditHyper #modalEdit #hostname').val(hyp.hostname);
                $('#modalEditHyper #modalEdit #user').val(hyp.user);
                $('#modalEditHyper #modalEdit #port').val(hyp.port);
                if(hyp.capabilities.disk_operations){
                    $('#modalEditHyper #modalEdit #capabilities-disk_operations').iCheck('check');
                }
                if(hyp.capabilities.hypervisor){
                    $('#modalEditHyper #modalEdit #capabilities-hypervisor').iCheck('check');
                }
                $('#modalEditHyper #modalEdit #viewer-static').val(hyp.viewer.static);
                $('#modalEditHyper #modalEdit #viewer-proxy_video').val(hyp.viewer.proxy_video);
                $('#modalEditHyper #modalEdit #viewer-spice_ext_port').val(hyp.viewer.spice_ext_port);
                $('#modalEditHyper #modalEdit #viewer-html5_ext_port').val(hyp.viewer.html5_ext_port);
                $('#modalEditHyper #modalEdit #viewer-hyper_vpn_host').val(hyp.isard_hyper_vpn_host);
                $('#modalEditHyper #modalEdit #viewer-proxy_hyper_host').val(hyp.viewer.proxy_hyper_host);
                
            });

            $.ajax({
                url: "/admin/table/hypervisors_pools",
                type: "POST",
                data: JSON.stringify({'order_by':'name'}),
                contentType: "application/json",
                success: function(pools)
                {
                    $.each(pools,function(key, value) 
                    {
                        $("#modalEditHyper #hypervisors_pools_dropdown").append('<option value=' + value.id + '>' + value.name + '</option>');
                    });
                },
                error: function (jqXHR, exception) {
                    processError(jqXHR,form)
                }
            });
            
            $('#modalEditHyper .capabilities_hypervisor').on('ifChecked', function(event){
                $('#modalEditHyper #viewer_fields').show()
                if( $('#modalEditHyper #viewer-static').val()!='' && $('#modalEditHyper #viewer-proxy_video').val()=='' && $('#modalEditHyper #viewer-proxy_hyper_host').val()==''){
                    $('#modalEditHyper #viewer-static').val($('#modalEditHyper #hostname').val());
                    $('#modalEditHyper #viewer-proxy_video').val($('#modalEditHyper #hostname').val());   
                    $('#modalEditHyper #viewer-proxy_hyper_host').val($('#modalEditHyper #hostname').val());                   
                }
                

            });


            $('#modalEditHyper .capabilities_hypervisor').on('ifUnchecked', function(event){
                $('#modalEditHyper #viewer_fields').hide()
                    $('#modalEditHyper #viewer-static').val('');
                    $('#modalEditHyper #viewer-proxy_video').val('');  
                    $('#modalEditHyper #viewer-proxy_hyper_host').val('');                
            });
            
            $('#modalEditHyper #send').off('click').on('click', function(e){
                    var form = $('#modalEditHyper #modalEdit');
                    form.parsley().validate();
                    if (form.parsley().isValid()){
                        data=$('#modalEditHyper #modalEdit').serializeObject();
                        delete data['capabilities-hypervisor']
                        delete data['capabilities-disk_operations']
                        data['capabilities'] = {}
                        data['capabilities']['hypervisor'] = $('#modalEditHyper #modalEdit #capabilities-hypervisor').prop('checked')
                        data['capabilities']['disk_operations'] = $('#modalEditHyper #modalEdit #capabilities-disk_operations').prop('checked')
                        data['hypervisors_pools'] = [$('#modalEditHyper #hypervisors_pools_dropdown').val()];
                            $.ajax({
                                type: "PUT",
                                url:"/admin/table/update/hypervisors",
                                data: JSON.stringify(data),
                                contentType: "application/json",
                                success: function(data)
                                    {
                                        $('form').each(function() { this.reset() });
                                        $('.modal').modal('hide');
                                    }
                            });
                    }
                });
    });               
    
    $('.btn-onlyforced').on('click', function () {

        var pk=$(this).closest("div").attr("data-pk");
        var only_forced = table.row("#"+pk).data()['only_forced'];        

        new PNotify({
            title: 'Confirmation Needed',
            text: "Are you sure you want to set \"only forced\" to: " + !only_forced + "?",
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
                url: "/admin/table/update/hypervisors",
                type: "PUT",
                data: JSON.stringify({'id': pk, 'only_forced': !only_forced}),
                contentType: "application/json",
                success: function(data) {
                    new PNotify({
                        title: 'Updated',
                        text: 'Hypervisor updated',
                        hide: true,
                        delay: 2000,
                        opacity: 1,
                        type: 'success'
                    })
                },
                error: function(data) {
                    new PNotify({
                        title: 'ERROR',
                        text: 'Could not update hypervisor',
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 2000,
                        opacity: 1
                    })
                },
            });

        }).on('pnotify.cancel', function() {
            });
    });

            
    //~ });

                                                
}


function renderEnabled(data){
    if(data.enabled==true){return '<i class="fa fa-check fa-2x" style="color:lightgreen"></i>';}
    return '<i class="fa fa-close fa-2x" style="color:darkgray"></i>';
}

function renderStatus(data){
        icon=data.icon;
        switch(data.status) {
            case 'Online':
                icon='<i class="fa fa-power-off fa-2x" style="color:green"></i>';
                break;
            case 'Offline':
                icon='<i class="fa fa-power-off fa-2x" style="color:black"></i>';
                break;
            case 'Error':
                icon='<i class="fa fa-exclamation-triangle fa-2x" style="color:lightred"></i>';
                break;
            case 'TryConnection':
                icon='<i class="fa fa-spinner fa-pulse fa-2x" style="color:lighblue"></i>';
                break;
            case 'ReadyToStart':
                icon='<i class="fa fa-thumbs-up fa-2x fa-fw" style="color:lightblue"></i>';
                break;
            case 'StartingThreads':
                icon='<i class="fa fa-cogs fa-2x" style="color:lightblue"></i>';
                break;
            case 'Blocked':
                icon='<i class="fa fa-lock fa-2x" style="color:lightred"></i>';
                break;
            case 'DestroyingDomains':
                icon='<i class="fa fa-bomb fa-2x" style="color:lightred"></i>';
                break;
            case 'StoppingThreads':
                icon='<i class="fa fa-hand-stop-o fa-2x" style="color:lightred"></i>';
                break;
            case 'Deleting':
                icon='<i class="fa fa-spinner fa-pulse fa-2x" style="color:lighblue"></i>';
                break;                  
            default:
                icon='<i class="fa fa-question fa-2x" style="color:lightred"></i>'
        }
        return icon+'<br>'+data.status;
}

function renderGraph(data){
    return '<div class="epoch category40" id="chart-'+data.id+'" style="width: 220px; height: 50px;"></div>'
}

