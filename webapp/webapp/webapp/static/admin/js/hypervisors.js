/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$hypervisor_template = $(".hyper-detail");

//~ var table =''
//~ tablepools=''
$(document).ready(function() {
    $('.admin-status').show()
    
    $('.btn-new-hyper').on('click', function () {
            $('#modalAddHyper').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            $("#modalAddHyper #hypervisors_pools_dropdown").find('option').remove();
            api.ajax('/isard-admin/admin/hypervisors_pools','GET','').done(function(pools) {
                $.each(pools,function(key, value) 
                {
                    $("#modalAddHyper #hypervisors_pools_dropdown").append('<option value=' + value.id + '>' + value.name + '</option>');
                });
            });

            $('#modalAddHyper .capabilities_hypervisor').on('ifChecked', function(event){
                $('#viewer_fields').show()
                if( $('#modalAddHyper #viewer-static').val()!='' && $('#modalAddHyper #viewer-proxy_video').val()=='' && $('#modalAddHyper #viewer-proxy_hyper_host').val()==''){
                    $('#modalAddHyper #viewer-static').val($('#modalAddHyper #hostname').val());
                    $('#modalAddHyper #viewer-proxy_video').val($('#modalAddHyper #hostname').val());
                    $('#modalAddHyper #viewer-proxy_hyper_host').val(0);                       
                }
                

            });


            $('#modalAddHyper .capabilities_hypervisor').on('ifUnchecked', function(event){
                $('#modalAddHyper #viewer_fields').hide()
                    $('#modalAddHyper #modalAddHyper #viewer-static').val('');
                    $('#modalAddHyper #modalAddHyper #viewer-proxy_video').val('');
                    $('#modalAddHyper #modalAddHyper #viewer-proxy_hyper_host').val(0);                   
            });
                        

            
    });

    $("#modalAddHyper #send").on('click', function(e){
            var form = $('#modalAddHyper #modalAdd');
            form.parsley().validate();
            if (form.parsley().isValid()){
                    data=$('#modalAddHyper #modalAdd').serializeObject();
                    socket.emit('hyper_add',data)
            }
        });










      function timestamp() { return (new Date).getTime() / 1000; }
      chart={}

    table = $('#hypervisors').DataTable( {
        "ajax": {
            "url": "/isard-admin/admin/hypervisors/json/",
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
                 "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
                },
            { "data": "enabled", "width": "10px" },
            { "data": "status", "width": "10px" },
            { "data": "hypervisor_number" , "width": "5px" },
            { "data": "id" , "width": "10px" },
            { "data": "hostname" , "width": "100px" },
            { "data": "info-qemu_version" , "width": "10px", "defaultContent": 'NaN'},
            { "data": "info-libvirt_version" , "width": "10px", "defaultContent": 'NaN' },
            { "data": "info-virtualization_capabilities" , "width": "10px", "defaultContent": 'NaN' },
            { "data": "info-memory_in_MB" , "width": "10px", "defaultContent": 'NaN' },
            { "data": "info-virtualization_capabilities" , "width": "10px", "defaultContent": 'NaN' },            
            { "data": "capabilities-disk_operations" , "width": "10px" },
            { "data": "capabilities-hypervisor" , "width": "10px" },
            { "data": "viewer-static" , "width": "10px" },
            { "data": "viewer-proxy_video" , "width": "10px" },
            { "data": "viewer-proxy_hyper_host" , "width": "10px" },
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
                            "targets": 9,
                            "render": function ( data, type, full, meta ) {
                                return Math.round(data/1024 * 10) / 10 +'GB';
                            }},
                            {
                            "targets": 10,
                            "render": function ( data, type, full, meta ) {
                                return full['info-cpu_cores']*full['info-threads_x_core'];
                            }},                                                           
                            {
                            "targets": 16,
                            "render": function ( data, type, full, meta ) {
                              return moment.unix(full.status_time).fromNow();
                            }}                          
             ],
             //~ "initComplete": function(settings, json) {
                        //~ this.api().rows().data().each(function(r){
                            //~ chart[r.id]=$("#chart-"+r.id).epoch({
                                            //~ type: "time.line",
                                            //~ axes: ["right"],
                                            //~ ticks: {right:1},
                                            //~ pixelRatio: 10,
                                            //~ fps: 60,
                                            //~ windowsSize: 60,
                                            //~ queueSize:120,
                                            //~ data: [
                                              //~ {label: "Load", values: [{x:0, y: 100}]},
                                              //~ {label: "Mem", values: [{x:0, y: 100}]}
                                             // {label: "Load", values: [{time: timestamp(), y: 100}]},
                                             // {label: "Mem", values: [{time: timestamp(), y: 100}]}
                                            //~ ]
                                          //~ });
                        //~ })
              //~ }                             
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
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/isard-admin/sio_admins');
     
    socket.on('connect', function() {
        connection_done();
        socket.emit('join_rooms',['hyper','domains_stats'])
        console.log('Listening admins and domains_stats namespace');
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
        chart[data.hyp_id].push([
        //~ chart.push([
          { time: timestamp(), y: data['cpu_percent-used']},
          { time: timestamp(), y: data['load-percent_free']}
        ]);
    });
        
    socket.on('hyper_deleted', function(data){
        var data = JSON.parse(data);
        //~ console.log('hyper deleted:'+data.id)
        //~ var row = table.row('#'+data.id).remove().draw();
         
        new PNotify({
                title: "Hypervisor deleted",
                text: "Hypervisor "+data.name+" has been deleted",
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
            return oldHtml.replace(/d.id/g, d.id).replace(/d.hostname/g, d.hostname);
        });
        return $newPanel
}

function setHypervisorDetailButtonsStatus(id,status){
          if(status=='Online'){
              $('#actions-domains-'+id+' *[class^="btn"]').prop('disabled', false);
              //~ $('#actions-enable-'+id+' *[class^="btn"]').prop('disabled', false);
              
          }else{
              $('#actions-domains-'+id+' *[class^="btn"]').prop('disabled', true);
          } 


          if(status=='Offline' || status=='Error'){
              $('#actions-delete-'+id+' .btn-delete').prop('disabled', false);
              
          }else{
              $('#actions-delete-'+id+' .btn-delete').prop('disabled', true);
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
          $('#actions-delete-'+id+' .btn-edit').prop('disabled', false);
          

}

function actionsHyperDetail(){
        $('.btn-enable').on('click', function () {
                var closest=$(this).closest("div");
                var pk=closest.attr("data-pk");
                var name=closest.attr("data-name");
                new PNotify({
                        title: 'Confirmation Needed',
                            text: "Are you sure you want to enable/disable: "+name+"?",
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
                            socket.emit('hyper_toggle',{'pk':pk,'name':name})
                        }).on('pnotify.cancel', function() {
                    }); 
                });

        $('.btn-delete').on('click', function () {
                var pk=$(this).closest("div").attr("data-pk");
                var name=$(this).closest("div").attr("data-name");
                new PNotify({
                        title: 'Confirmation Needed',
                            text: "Are you sure you want to delete hypervisor: "+name+"?",
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
                            socket.emit('hyper_delete',{'pk':pk,'name':name})
                        }).on('pnotify.cancel', function() {
                }); 
            });  

        $('.btn-domstop').on('click', function () {
                var pk=$(this).closest("div").attr("data-pk");
                var name=$(this).closest("div").attr("data-name");
                new PNotify({
                        title: 'Confirmation Needed',
                            text: "Are you sure you want to FORCE stop all domains in hypervisor: "+name+"?",
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
                            socket.emit('hyper_domains_stop',{'pk':pk,'name':name,'without_viewer':false})
                        }).on('pnotify.cancel', function() {
                }); 
            }); 

        $('.btn-domstop-woviewer').on('click', function () {
                var pk=$(this).closest("div").attr("data-pk");
                var name=$(this).closest("div").attr("data-name");
                new PNotify({
                        title: 'Confirmation Needed',
                            text: "Are you sure you want to FORCE stop all domains in hypervisor "+name+" that doesn't have a client viewer now?",
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
                            socket.emit('hyper_domains_stop',{'pk':pk,'name':name,'without_viewer':true})
                        }).on('pnotify.cancel', function() {
                }); 
            });
            

    $('.btn-edit').on('click', function () {
                var pk=$(this).closest("div").attr("data-pk");
                var name=$(this).closest("div").attr("data-name");
            $("#modalEdit")[0].reset();
            $("#modalEditHyper #hypervisors_pools_dropdown").find('option').remove();
            
            $('#modalEditHyper').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');

            api.ajax('/isard-admin/admin/load/hypervisors/post','POST',{'id':pk}).done(function(hyp) {
                $('#modalEditHyper #modalEdit #id').val(pk);
                $('#modalEditHyper #modalEdit #fake_id').val(pk);
                $('#modalEditHyper #modalEdit #description').val(hyp.description);
                if(hyp.id == 'isard-hypervisor'){
                    $('#modalEditHyper #modalEdit #hypervisor_number').val(0);
                    $('#modalEditHyper #modalEdit #hypervisor_number').prop( "disabled", true );
                }else{
                    $('#modalEditHyper #modalEdit #hypervisor_number').val(hyp.hypervisor_number);
                    $('#modalEditHyper #modalEdit #hypervisor_number').prop( "disabled", false );
                }
                $('#modalEditHyper #modalEdit #hostname').val(hyp.hostname);
                $('#modalEditHyper #modalEdit #user').val(hyp.user);
                $('#modalEditHyper #modalEdit #port').val(hyp.port);
                if(hyp['capabilities-disk_operations']){
                    $('#modalEditHyper #modalEdit #capabilities-disk_operations').iCheck('check');
                }
                if(hyp['capabilities-hypervisor']){
                    $('#modalEditHyper #modalEdit #capabilities-hypervisor').iCheck('check');
                }                
                //~ $('#modalEditHyper #modalEdit #capabilities-disk_operations').val(hyp['capabilities']['disk_operations']);
                //~ $('#modalEditHyper #modalEdit #capabilities-hypervisor').val(hyp['capabilities']['hypervisor']);
                $('#modalEditHyper #modalEdit #viewer-static').val(hyp['viewer-static']);
                $('#modalEditHyper #modalEdit #viewer-proxy_video').val(hyp['viewer-proxy_video']);
                $('#modalEditHyper #modalEdit #viewer-proxy_hyper_host').val(hyp['viewer-proxy_hyper_host']);
                
            });
           api.ajax('/isard-admin/admin/hypervisors_pools','GET','').done(function(pools) {
                
                $.each(pools,function(key, value) 
                {
                    $("#modalEditHyper #hypervisors_pools_dropdown").append('<option value=' + value.id + '>' + value.name + '</option>');
                });
                //Set selected!
                
            });            
             //~ $('#hardware-block').hide();
            //~ $('#modalEdit').parsley();
            //~ modal_edit_desktop_datatables(pk);



            
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
            
            $('#modalEditHyper #send').on('click', function(e){
                    var form = $('#modalEditHyper #modalEdit');
                    form.parsley().validate();
                    if (form.parsley().isValid()){
                            data=$('#modalEditHyper #modalEdit').serializeObject();
                            //~ console.log(data)
                            socket.emit('hyper_edit',data)
                    }
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

