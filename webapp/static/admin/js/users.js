/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$(document).ready(function() {

	$('.btn-new-user').on('click', function () {
			$('#modalAddUser').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalAddUserForm')[0].reset();
            setModalAddUser();
	});

	$('.btn-new-role').on('click', function () {
        setQuotaOptions();
			$('#modalAddRole').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalAddRoleForm')[0].reset();
            //~ setModalAddUser();
	});
        
    var table=$('#users').DataTable( {
        "ajax": {
            "url": "/admin/users/get",
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
            { "data": "active"},
            { "data": "id"},
            { "data": "name"},
            { "data": "kind"},
            { "data": "category"},
            { "data": "group"},
            { "data": "role"},
            {
                "data": null,
                className: "center xe-password",
                "defaultContent": '  \
                                <div><i class="fa fa-lock"></i> \
                              </div>'
            },
            { "data": "accessed"}],
			 "columnDefs": [
							{
							"targets": 9,
							"render": function ( data, type, full, meta ) {
							  return moment.unix(full.accessed).toISOString("YYYY-MM-DDTHH:mm:ssZ"); //moment.unix(full.accessed).fromNow();
							}}
             ]
        });
    //~ });

    $('#users').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = table.row( tr );
 
        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            // Open this row
            row.child( format(row.data()) ).show();
            //~ editData();
            tr.addClass('shown');
        }
    });
});

function format ( d ) {
    // `d` is the original data object for the row
    var cells='<div class="btn-group"> \
                                <button class="btn btn-sm btn-default btn-edit" id="btn-edit" type="button"  data-placement="top" data-toggle="tooltip" data-original-title="Edit"><i class="fa fa-pencil"></i></button> \
                              </div>';
    for(var k in d){
		cells+='<tr>'+
					'<td>'+k+':</td>'+
					'<td>'+d[k]+'</td>'+
				'</tr>'
	}
    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">'+
        cells;
    '</table>';
}

    function setModalAddUser(){
        api.ajax_async('/admin/userschema','POST','').done(function(d) {
            $.each(d, function(key, value) {
                $("#" + key).find('option').remove().end();
                for(var i in d[key]){
                    $("#"+key).append('<option value=' + value[i].id + '>' + value[i].name + '</option>');
                }
            });
                
        });
    }
