/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$(document).ready(function() {
    
	$('.btn-new').on('click', function () {
            $("#modalAddMediaForm")[0].reset();
			$('#modalAddMedia').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalAddMediaForm').parsley();
            setAlloweds_add('#alloweds-add');
	});

    var table=$('#media').DataTable( {
        "ajax": {
            "url": "/admin/table/media/get",
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
            { "data": "icon"},
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
							  return renderIcon(full);
							}},
							{
							"targets": 1,
							"render": function ( data, type, full, meta ) {
							  return renderName(full);
							}},
                            {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
							  return renderProgress(full);
							}}],
        "initComplete": function() {
                                //~ $('.progress .progress-bar').progressbar();
                                //~ $('.progress-bar').progressbar();
                              }
    } );

    $('#media').find(' tbody').on( 'click', 'button', function () {
        var data = table.row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
            case 'btn-delete':
				new PNotify({
						title: 'Confirmation Needed',
							text: "Are you sure you want to delete media: "+data.name+"?",
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
                            socket.emit('media_update',{'pk':data.id,'name':'status','value':'Deleting'})
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
    
    $("#modalAddMedia #send").on('click', function(e){
            var form = $('#modalAddMediaForm');

            form.parsley().validate();

            if (form.parsley().isValid()){
                data=$('#modalAddMediaForm').serializeObject();
                data=replaceAlloweds_arrays(data)
                socket.emit('media_add',data)
            }
            

        });

    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_admins');
     
    socket.on('connect', function() {
        connection_done();
        socket.emit('join_rooms',['media'])
        console.log('Listening media namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
    socket.on('user_quota', function(data) {
        console.log('Quota update')
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

    socket.on('media_data', function(data){
        console.log('add or update')
        var data = JSON.parse(data);
            //~ $('#pbid_'+data.id).data('transitiongoal',data.percentage);
            //~ $('#pbid_').css('width', data.percentage+'%').attr('aria-valuenow', data.percentage).text(data.percentage); 
            //~ $('#psmid_'+data.id).text(data.percentage);
        dtUpdateInsert(table,data,false);
        //~ $('.progress .progress-bar').progressbar();
    });

    
    socket.on('media_delete', function(data){
        console.log('delete')
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
            return '<div class="progress"> \
  <div id="pbid_'+data.id+'" class="progress-bar" role="progressbar" aria-valuenow="'+data.percentage+'" \
  aria-valuemin="0" aria-valuemax="100" style="width:'+data.percentage+'%"> \
    '+data.percentage+'% \
  </div> \
</<div> '
}

function renderName(data){
		return '<div class="block_content" > \
      			<h2 class="title" style="height: 4px; margin-top: 0px;"> \
                <a>'+data.name+'</a> \
                </h2> \
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
