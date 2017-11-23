/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$(document).ready(function() {

	$('.btn-new').on('click', function () {
            $("#modalAddIsoForm")[0].reset();
			$('#modalAddIso').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalAddIsoForm').parsley();
            setAlloweds_add('#alloweds-add');
	});

    var table=$('#isos').DataTable( {
        "ajax": {
            "url": "/admin/table/isos/get",
            "dataSrc": ""
        },
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
			"deferRender": true,
        "columns": [
				//~ {
                //~ "className":      'details-control',
                //~ "orderable":      false,
                //~ "data":           null,
                //~ "width": "10px",
                //~ "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				//~ },
            { "data": "name"},
            { "data": "status"},
            { "data": "progress"},
            {
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "width": "10px",
                "defaultContent": '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
			}, 
        ],
        "columnDefs": [ 
							{
							"targets": 0,
							"render": function ( data, type, full, meta ) {
							  return renderName(full);
							}},
                            {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
							  return renderProgress(full);
							}}],
        "initComplete": function() {
                                $('.progress .progress-bar').progressbar();
                              }
    } );

    $('#isos').find(' tbody').on( 'click', 'button', function () {
        var data = table.row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
            case 'btn-delete':
				new PNotify({
						title: 'Confirmation Needed',
							text: "Are you sure you want to delete iso: "+data.name+"?",
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
                            socket.emit('iso_update',{'pk':data.id,'name':'status','value':'Deleting'})
						}).on('pnotify.cancel', function() {
				});	                        
                break;
        };
    });

	$('.btn-delete').on('click', function () {
				var pk=$(this).closest("div").attr("data-pk");
				var name=$(this).closest("div").attr("data-name");
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
							stack: stack_center
						}).get().on('pnotify.confirm', function() {
                            socket.emit('domain_update',{'pk':pk,'name':'status','value':'Deleting'})
						}).on('pnotify.cancel', function() {
				});	
	});
    
    $("#modalAddIso #send").on('click', function(e){
            var form = $('#modalAddIsoForm');

            form.parsley().validate();

            if (form.parsley().isValid()){
                data=$('#modalAddIsoForm').serializeObject();
                data=replaceAlloweds_arrays(data)
                socket.emit('iso_add',data)
            }
            

        });
        
    // SocketIO
    reconnect=-1;
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_users');
    console.log(socket)
     
    socket.on('connect', function() {
        connection_done();
        reconnect+=1;
        if(reconnect){
            console.log(reconnect+' reconnects to websocket. Refreshing datatables');
            table.ajax.reload();
            // Should have a route to update quota via ajax...
        }
        console.log('Listening users namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
    socket.on('user_quota', function(data) {
        console.log('Quota update')
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

    socket.on('iso_data', function(data){
        console.log('add or update')
        var data = JSON.parse(data);
        $('.progress .progress-bar').progressbar();
        dtUpdateInsert(table,data,false);
    });
    
    socket.on('iso_delete', function(data){
        console.log('delete')
        var data = JSON.parse(data);
        var row = table.row('#'+data.id).remove().draw();
        new PNotify({
                title: "Iso deleted",
                text: "Iso "+data.name+" has been deleted",
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
            $("#modalAddIsoForm")[0].reset();
            $("#modalAddIso").modal('hide');
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

    
 } );

function renderProgress(data){
    return '<div class="progress progress_sm"> \
                <div class="progress-bar bg-green" role="progressbar" data-transitiongoal="'+data.percentage+'"></div> \
            </div> \
            <small>'+data.percentage+'% Complete</small>' 
}

function renderName(data){
		return '<div class="block_content" > \
      			<h2 class="title" style="height: 4px; margin-top: 0px;"> \
                <a>'+data.name+'</a> \
                </h2> \
      			<p class="excerpt" >'+data.description+'</p> \
           		</div>'
}
