/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

//~ tables=['roles','categories','groups']
$(document).ready(function() {
    var table=$('#roles').DataTable( {
        "ajax": {
            "url": "/admin/table/roles/get",
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
            { "data": "name", className: "xe-name" },
            { "data": "description", className: "xe-description"}
        ]
    } );

    $('#roles').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = table.row( tr );
 
        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            // Open this row
            row.child( formatRoles(row.data()) ).show();
            //~ editRole();
            tr.addClass('shown');
        }
    });

	$('.btn-new-role').on('click', function () {
        setQuotaOptions('#roles-quota');
			$('#modalAddRole').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalAddRoleForm')[0].reset();
            //~ setModalAddUser();
	});    

    $("#modalAddRole #send").on('click', function(e){
            var form = $('#modalAddRoleForm');
            form.parsley().validate();
            if (form.parsley().isValid()){
                data=$('#modalAddRoleForm').serializeObject();
                data['table']='roles';
                socket.emit('role_category_group_add',data)  
            }
        }); 
            
});

function formatRoles ( d ) {
    // `d` is the original data object for the row
    var cells=''
            //~ '<div class="btn-group"> \
                    //~ <button class="btn btn-sm btn-default btn-edit" id="btn-edit" type="button"  data-placement="top" data-toggle="tooltip" data-original-title="Edit"><i class="fa fa-pencil"></i></button> \
               //~ </div>';
    for(var k in d){
		cells+='<tr>'+
					'<td>'+k+':</td>'+
					'<td>'+d[k]+'</td>'+
				'</tr>'
	}
    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">'+
        cells+
    '</table>';
}
