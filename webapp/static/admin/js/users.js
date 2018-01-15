/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$(document).ready(function() {

	$('.btn-new-user').on('click', function () {
        setQuotaOptions('#users-quota');
        $('#modalAddUser').modal({backdrop: 'static', keyboard: false}).modal('show');
        $('#modalAddUserForm')[0].reset();
        setModalAddUser();
	});

    $("#modalAddUser #send").on('click', function(e){
        var form = $('#modalAddUserForm');
        form.parsley().validate();
        if (form.parsley().isValid()){
            
            data=quota2dict($('#modalAddUserForm').serializeObject());
            delete data['password2']
            console.log(data)
            socket.emit('user_add',data)
        }
    }); 


    $("#modalAddUser #role").on('change', function(e){
        console.log($(this).val())
        setHardwareDomainDefaults('#users-quota','_aillera_M2')
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
            { "data": "active", "width": "10px"},
            { "data": "id"},
            { "data": "name"},
            { "data": "role", "width": "10px"},
            { "data": "category", "width": "10px"},
            { "data": "group", "width": "10px"},
            { "data": "kind", "width": "10px"},
            //~ {
                //~ "data": null,
                //~ className: "center xe-password",
                //~ "defaultContent": '  \
                                //~ <div><i class="fa fa-lock"></i> \
                              //~ </div>'
            //~ },
            { "data": "accessed"},
            { "data": "base", "width": "10px"},
            { "data": "user_template", "width": "10px"},
            { "data": "public_template", "width": "10px"},
            { "data": "desktops", "width": "10px"}],
			 "columnDefs": [
							{
							"targets": 1,
							"render": function ( data, type, full, meta ) {
                                if(full.active==true){return '<i class="fa fa-check" style="color:lightgreen"></i>';}
                                return '<i class="fa fa-close" style="color:darkgray"></i>';
							}},
							{
							"targets": 8,
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



    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_admins');
     
    socket.on('connect', function() {
        connection_done();
        socket.emit('join_rooms',['users'])
        console.log('Listening users namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });

    socket.on('add_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $("#modalAddUserForm")[0].reset();
            $("#modalAddUser").modal('hide');
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
       
    //~ socket.on('user_quota', function(data) {
        //~ console.log('Quota update')
        //~ var data = JSON.parse(data);
        //~ drawUserQuota(data);
    //~ });
    
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
        cells+
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
