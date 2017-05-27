/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$hypervisor_template = $(".hyper-detail");

$(document).ready(function() {
	$('.btn-new-hyper').on('click', function () {
			$('#modalAddHyper').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
	});
    
    var table = $('#hypervisors').DataTable( {
        "ajax": {
            "url": "/admin/hypervisors/json",
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
            { "data": "id" , "width": "10px" },
            { "data": "enabled", "width": "10px" },
            { "data": "status", "width": "10px" },
            { "data": "hostname", "width": "10px" },
            { "data": "hypervisors_pools", "width": "10px" },
            { "data": "status_time" , "width": "10px" },
            { "data": "description", "visible": false}],
			 "order": [[4, 'asc']],
			 "columnDefs": [ {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
							  return renderEnabled(full);
							}},
							{
							"targets": 3,
							"render": function ( data, type, full, meta ) {
							  return renderStatus(full);
							}},
							{
							"targets": 4,
							"render": function ( data, type, full, meta ) {
							  return renderName(full);
							}},
							{
							"targets": 6,
							"render": function ( data, type, full, meta ) {
							  return moment.unix(full.status_time).fromNow();
							}}
             ]
    } );

	$('#hypervisors').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = table.row( tr );
		
        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            // Close other rows
             if ( table.row( '.shown' ).length ) {
                      $('.details-control', table.row( '.shown' ).node()).click();
              }
            // Open this row
            row.child( formatHypervisorPanel(row.data()) ).show();
            tr.addClass('shown');
            $('#status-detail-'+row.data().id).html(row.data().detail);
            actionsHyperDetail();

        }
    } );

    $("#modalAddHyper #send").on('click', function(e){
            var form = $('#modalAddHyper #modalAdd');
            console.log('inside')
            //~ form.parsley().validate();
            //~ var queryString = $('#modalAdd').serialize();
            data=$('#modalAddHyper #modalAdd').serializeObject();
            console.log(data)
            socket.emit('hypervisor_add',data)
            //~ if (form.parsley().isValid()){
                //~ template=$('#modalAddDesktop #template').val();
                //~ console.log('TEMPLATE:'+template)
                //~ if (template !=''){
                    //~ var queryString = $('#modalAdd').serialize();
                    //~ data=$('#modalAdd').serializeObject();
                    //~ socket.emit('domain_add',data)
                //~ }else{
                    //~ $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    //~ $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                //~ }
            //~ }
        });
        
    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_admins');
     
    socket.on('connect', function() {
        connection_done();
        socket.emit('join_rooms',['hyper'])
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
        console.log('add or update')
        var data = JSON.parse(data);
		if($("#" + data.id).length == 0) {
		  //it doesn't exist
		  table.row.add(data).draw();
		}else{
          //if already exists do an update (ie. connection lost and reconnect)
          var row = table.row('#'+data.id); 
          table.row(row).data(data).invalidate();			
		}
        table.draw(false);
    });

    socket.on('hyper_status', function(data){
        console.log('status: '+data.name)
    });
        
    socket.on('hyper_delete', function(data){
        console.log('delete')
        var data = JSON.parse(data);
        var row = table.row('#'+data.id).remove().draw();
        new PNotify({
                title: "Hypervisor deleted",
                text: "Hypervisor "+data.name+" has been deleted",
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


    //~ // Stream hypers
	//~ if (!!window.EventSource) {
	  //~ var hyper_source = new EventSource('/stream/admin/hypers');
	//~ } else {
	  //~ // Result to xhr polling :(
	//~ }

	//~ window.onbeforeunload = function(){
	  //~ hyper_source.close();
	//~ };

	//~ hyper_source.addEventListener('New', function(e) {
	  //~ var data = JSON.parse(e.data);
		//~ if($("#" + data.id).length == 0) {
		  //~ //it doesn't exist
		  //~ table.row.add( formatHypervisorData(data)).draw();
		//~ }else{
		  //~ //if already exists do an update (ie. connection lost and reconnect)
			//~ var row = table.row('#'+data.id); 
			//~ table.row(row).data(formatHypervisorData(data));			
		//~ }
	//~ }, false);

	//~ //Source for table updates hypervisors
	//~ hyper_source.addEventListener('hypervisors', function(e) {
	  //~ var data = JSON.parse(e.data);
      //~ var row = table.row('#'+data.id); 
      //~ table.row(row).data(formatHypervisorData(data));
	//~ }, false);

	//~ hyper_source.addEventListener('Deleted', function(e) {
	  //~ var data = JSON.parse(e.data);
      //~ var row = table.row('#'+data.id); 
      //~ table.row(row).remove();
	//~ }, false);

	//~ hyper_source.addEventListener('hypervisors_status', function(e) {
        //~ // Here will be the stats
	//~ }, false);
	
	//~ hyper_source.addEventListener('error', function(e) {
        //~ console.log('Hyper sse Error');
        //~ if (e.readyState == EventSource.CLOSED) {
		//~ // Connection was closed.
	  //~ }
	//~ }, false);
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

function actionsHyperDetail(){
		$('.btn-edit').on('click', function () {
            //Not implemented
			});

		$('.btn-kind').on('click', function () {
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
							stack: stack_center
						}).get().on('pnotify.confirm', function() {
                            console.log(pk);
							api.ajax('/admin/hypervisors/toggle','POST',{'pk':pk,'name':'enabled'}).done(function(data) {
							});  
						}).on('pnotify.cancel', function() {
                    });	
                });

		$('.btn-delete').on('click', function () {
				var pk=$(this).closest("div").attr("data-pk");
				var name=$(this).closest("div").attr("data-name");
				new PNotify({
						title: 'Confirmation Needed',
							text: "Are you sure you want to delete hypervisor: "+name+"?\n",
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
							stack: stack_center
						}).get().on('pnotify.confirm', function() {
							api.ajax('/admin/hypervisors_update','POST',{'pk':pk,'name':'status','value':'Deleting'}).done(function(data) {
							});  
						}).on('pnotify.cancel', function() {
				});	
			});
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

