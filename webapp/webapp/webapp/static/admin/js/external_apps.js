/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

//~ tables=['roles','categories','groups']
$(document).ready(function() {
    var table=$('#externalapps').DataTable( {
        "ajax": {
            "url": "/admin/table/secrets",
            "dataSrc": "",
            "type" : "POST",
            "data": function(d){return JSON.stringify({})}
        },
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "columns": [
            { "data": "id"},
            { "data": "secret"},
            { "data": "description"},
            { "data": "role_id"},
            { "data": "category_id"},
            { "data": "domain"},
        ]
    } );

    
	$('.btn-new-role').on('click', function () {
        setQuotaMax('#roles-quota');
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
