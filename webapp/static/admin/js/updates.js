/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/
table={}
$(document).ready(function() {
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




    table['domains']=$('#domains_tbl').DataTable({
			"ajax": {
				"url": "/admin/updates/domains",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No updates available"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
                {"data": null,
                 'defaultContent': ''},
				{"data": "icon"},
				{"data": "name"},
                {"data": null,
                 'defaultContent': ''},
                {"data": null,
                 'defaultContent': ''},                 
				//~ { "data": "description"},
				//~ {
                //~ "className":      'actions-control',
                //~ "orderable":      false,
                //~ "data":           null,
                //~ "defaultContent": '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
				//~ },                
                ],
			 "order": [[0, 'desc'],[1,'desc'],[2,'asc']],
			 "columnDefs": [{
							"targets": 0,
							"render": function ( data, type, full, meta ) {
                                if(!(full['new'])){
                                    return '<span class="label label-success pull-right">New</span>';
                                }
							}},
                            {
							"targets": 1,
							"render": function ( data, type, full, meta ) {
                                return renderIcon(full)
							}},
                            {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
                                return renderName(full)
							}},
                            {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
                                if("progress" in full){
                                    return renderProgress(full);
                                }
							}},
                            {
							"targets": 4,
							"render": function ( data, type, full, meta ) {
                                //~ console.log(full.status+' '+full.id)
                                if(!('status' in full)){
                                    return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
                                }
                                return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                //~ if(full.status == 'Downloaded' || full.status == 'Stopped'){
                                    //~ return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                //~ }                                
							}}],
                "initComplete": function(settings, json){
                     socket.on('domains_data', function(data){
                        console.log('domains data')
                        var data = JSON.parse(data);
                            //~ console.log(data)
                        dtUpdateInsert(table['domains'],data,false);
                    });                   
                }                            
                            
                            
    } );

    $('#domains_tbl').find(' tbody').on( 'click', 'button', function () {
        var data = table['domains'].row( $(this).parents('tr') ).data();
        console.log($(this).attr('id'),data);
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });



    table['media']=$('#media_tbl').DataTable({
			"ajax": {
				"url": "/admin/updates/media",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No updates available"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
                {"data": null,
                 'defaultContent': ''},
				{"data": "icon"},
				{"data": "name"},
                {"data": null,
                 'defaultContent': ''},
				//~ { "data": "description"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[0, 'desc'],[1,'desc'],[2,'asc']],
			 "columnDefs": [{
							"targets": 0,
							"render": function ( data, type, full, meta ) {
                                if(!(full['new'])){
                                    return '<span class="label label-success pull-right">New</span>';
                                }
							}},
                            {
							"targets": 1,
							"render": function ( data, type, full, meta ) {
                                return renderIcon(full)
							}},
                            {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
                                return renderName(full)
							}},
                            {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
                                if("progress" in full){
                                    return renderProgress(full);
                                }
							}}],
                "initComplete": function(settings, json){
                     socket.on('media_data', function(data){
                        console.log('add or update')
                        var data = JSON.parse(data);
                            console.log('media update')
                        dtUpdateInsert(table['media'],data,false);
                    });                   
                }
                            
                            
    } );




    $('#media_tbl').find(' tbody').on( 'click', 'button', function () {
        var data = table['media'].row( $(this).parents('tr') ).data();
        console.log($(this).attr('id'),data);
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });
    
    table['builders']=$('#builders_tbl').DataTable({
			"ajax": {
				"url": "/admin/updates/builders",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No updates available"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{"data": "icon"},
				{ "data": "name"},
				//~ { "data": "description"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[1, 'asc']],
			 "columnDefs": [ {
							"targets": 0,
							"render": function ( data, type, full, meta ) {
							  return renderIcon(full);
							}}]
    } );

    $('#builders_tbl').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
        console.log($(this).attr('id'),data);
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });
    
    table['virt_builder']=$('#virt_builder_tbl').DataTable({
			"ajax": {
				"url": "/admin/updates/virt_builder",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No updates available"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{"data": "icon"},
				{ "data": "name"},
				//~ { "data": "description"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[1, 'asc']],
			 "columnDefs": [ {
							"targets": 0,
							"render": function ( data, type, full, meta ) {
							  return renderIcon(full);
							}}]
    } );

    $('#virt_builder_tbl').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
        console.log($(this).attr('id'),data);
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });
    
    table['virt_install']=$('#virt_install_tbl').DataTable({
			"ajax": {
				"url": "/admin/updates/virt_install",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No updates available"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{"data": "icon"},
				{ "data": "name"},
				//~ { "data": "description"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[1, 'asc']],
			 "columnDefs": [ {
							"targets": 0,
							"render": function ( data, type, full, meta ) {
							  return renderIcon(full);
							}}]
    } );

    $('#virt_install_tbl').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
        console.log($(this).attr('id'),data);
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });
    
    $('.update-all').on( 'click', function () {
      id=$(this).attr('id')
      api.ajax('/admin/updates/update/'+id,'POST',{}).done(function(data) {
          console.log(id)
          table[id].ajax.reload();
          //~ if(id == 'virt_install'){virt_install_table.ajax.reload();}
      }); 
      // invalidate table
     
    })

    //~ $('.update-one').on( 'click', function () {
      //~ id=$(this).attr('id')
          //~ console.log(id)
     
    //~ })
 
});


function renderName(data){
		return '<div class="block_content" > \
      			<h2 class="title" style="height: 4px; margin-top: 0px;"> \
                <a>'+data.name+'</a> \
                </h2> \
      			<p class="excerpt" >'+data.description+'</p> \
           		</div>'
}

function renderProgress(data){
            return '<div class="progress"> \
  <div id="pbid_'+data.id+'" class="progress-bar" role="progressbar" aria-valuenow="'+data['progress']['% Total']+'" \
  aria-valuemin="0" aria-valuemax="100" style="width:'+data['progress']['% Total']+'%"> \
    '+data['progress']['% Total']+'% \
  </div> \
</<div> '
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
