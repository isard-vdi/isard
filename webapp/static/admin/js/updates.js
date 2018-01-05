/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/
table={}
$(document).ready(function() {

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

    $('#domains_tbl').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
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

    $('#media_tbl').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
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
    
    $('.update').on( 'click', function () {
      id=$(this).attr('id')
      api.ajax('/admin/updates/update/'+id,'POST',{}).done(function(data) {
          console.log(id)
          table[id].ajax.reload();
          //~ if(id == 'virt_install'){virt_install_table.ajax.reload();}
      }); 
      // invalidate table
     
    })
        
});




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
