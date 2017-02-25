/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$(document).ready(function() {

    int_table=$('#interfaces').DataTable({
			"ajax": {
				"url": "/admin/table/interfaces/get",
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
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
				{ "data": "name"},
				{ "data": "description"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[1, 'asc']]
    } );

    $('#interfaces').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
        console.log($(this).attr('id'),data);
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });

    
    // DISKS
    disks_table=$('#disks').DataTable({
			"ajax": {
				"url": "/admin/table/disks/get",
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
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
				{ "data": "name"},
				{ "data": "description"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[1, 'asc']]
    } );

    $('#disks').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
        console.log($(this).attr('id'),data);
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });

    
    // GRAPHICS
    graphics_table=$('#graphics').DataTable({
			"ajax": {
				"url": "/admin/table/graphics/get",
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
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
				{ "data": "name"},
				{ "data": "description"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[1, 'asc']]
    } );

    $('#graphics').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
        console.log($(this).attr('id'),data);
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });
    
    
    // VIDEOS
    videos_table=$('#videos').DataTable({
			"ajax": {
				"url": "/admin/table/videos/get",
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
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
				{ "data": "name"},
				{ "data": "description"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[1, 'asc']]
    } );

    $('#videos').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
        console.log($(this).attr('id'),data);
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });
});
