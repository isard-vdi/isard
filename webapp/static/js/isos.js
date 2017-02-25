/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$(document).ready(function() {
    var table=$('#isos').DataTable( {
        "ajax": {
            "url": "/admin/table/isos/get",
            "dataSrc": ""
        },
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
        "columns": [
				{
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
            { "data": "status"},
            { "data": "name"},
            { "data": "description"}
        ],
        "columnDefs": [ {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
							  return renderProgress(full);
							}}],
        "initComplete": function() {
                                $('.progress .progress-bar').progressbar();
                              }
    } );
    
 } );

function renderProgress(data){
    return '<div class="progress progress_sm"> \
                <div class="progress-bar bg-green" role="progressbar" data-transitiongoal="57"></div> \
            </div> \
            <small>57% Complete</small>' 
}
