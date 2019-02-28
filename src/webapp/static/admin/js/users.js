/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var table= ''
$(document).ready(function() {

    $template = $(".template-detail-users");
    
	$('.btn-new-user').on('click', function () {
        setQuotaOptions('#users-quota');
        $('#modalAddUser').modal({backdrop: 'static', keyboard: false}).modal('show');
        $('#modalAddUserForm')[0].reset();
        setModalUser();
	});


    
	$('.btn-new-bulkusers').on('click', function () {
        setQuotaOptions('#bulkusers-quota');
        $('#modalAddBulkUsers').modal({backdrop: 'static', keyboard: false}).modal('show');
        $('#modalAddBulkUsersForm')[0].reset();
        setModalUser();
	});

	$('#btn-download-bulkusers').on('click', function () {
        var viewerFile = new Blob(["username,name,mail,password\njdoe,John Doe,jdoe@isardvdi.com,sup3rs3cr3t\nauser,Another User,auser@domain.com,a1sera1ser"], {type: "text/csv"});
        var a = document.createElement('a');
            a.download = 'bulk-users-template.csv';
            a.href = window.URL.createObjectURL(viewerFile);
        var ev = document.createEvent("MouseEvents");
            ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
            a.dispatchEvent(ev);  
	});
    
	$('.btn-old-users').on('click', function () {
        $('#modalOldUsers').modal({backdrop: 'static', keyboard: false}).modal('show');
        populate_users_table()
        //~ $('#modalAddUserForm')[0].reset();
        //~ setModalUser();
	});
    
    $("#modalAddUser #send").on('click', function(e){
        var form = $('#modalAddUserForm');
        data=quota2dict($('#modalAddUserForm').serializeObject());
        form.parsley().validate();
        if (form.parsley().isValid()){
            
            data=quota2dict($('#modalAddUserForm').serializeObject());
            delete data['password2']
            data['id']=data['username']=$('#modalAddUserForm #id').val();
            socket.emit('user_add',data)
        }
    }); 

    $("#modalEditUser #send").on('click', function(e){
        var form = $('#modalEditUserForm');
        data=quota2dict($('#modalEditUserForm').serializeObject());
        form.parsley().validate();
        if (form.parsley().isValid()){
            
            data=quota2dict($('#modalEditUserForm').serializeObject());
            //~ delete data['password2']
            data['id']=data['username']=$('#modalEditUserForm #id').val();
            socket.emit('user_edit',data)
        }
    }); 

    $("#modalPasswdUser #send").on('click', function(e){
        var form = $('#modalPasswdUserForm');
        form.parsley().validate();
        if (form.parsley().isValid()){
            data={}
            data['id']=data['username']=$('#modalPasswdUserForm #id').val();
            data['name']=$('#modalPasswdUserForm #name').val();
            data['password']=$('#modalPasswdUserForm #password').val();
            socket.emit('user_passwd',data)
        }
    }); 

    $("#modalDeleteUserTree #send").on('click', function(e){
        //~ var form = $('#modalDeleteUserForm');
        //~ data=$('#modalDeleteUserForm').serializeObject();
        //~ form.parsley().validate();
        //~ if (form.parsley().isValid()){
            
            //~ data=quota2dict($('#modalDeleteUserForm').serializeObject());
            //~ socket.emit('user_delete',data)
        //~ }
    }); 
            
    //~ $("#modalDeleteUser #send").on('click', function(e){
        //~ var form = $('#modalDeleteUserForm');
        //~ data=$('#modalDeleteUserForm').serializeObject();
        //~ form.parsley().validate();
        //~ if (form.parsley().isValid()){
            
            //~ data=quota2dict($('#modalDeleteUserForm').serializeObject());
            //~ socket.emit('user_delete',data)
        //~ }
    //~ }); 

       document.getElementById('csv').addEventListener('change', readFile, false);
       var filecontents=''
       function readFile (evt) {
           var files = evt.target.files;
           var file = files[0];           
           var reader = new FileReader();
           reader.onload = function(event) {
             filecontents=event.target.result;            
           }
           reader.readAsText(file, 'UTF-8')
        }

        function toObject(names, values) {
            var result = {};
            for (var i = 0; i < names.length; i++)
                 result[names[i]] = values[i];
            return result;
        }

    function parseCSV(){
        lines=filecontents.split('\n')
        header=lines[0].split(',')
        users=[]
        $.each(lines, function(n, l){
            if(n!=0 && l.length > 10){
                usr=toObject(header,l.split(','))
                usr['id']=usr['username']
                users.push(usr)
            }
        })
        return users;
    }
        
    $("#modalAddBulkUsers #send").on('click', function(e){
        var form = $('#modalAddBulkUsersForm');
        form.parsley().validate();
        
        if (form.parsley().isValid()){
            data=quota2dict($('#modalAddBulkUsersForm').serializeObject());
            users=parseCSV()
            socket.emit('bulkusers_add',{'data':data,'users':users})
        }
    }); 

    $("#add-role").on('change', function(e){
         setQuotaTableDefaults('#users-quota','roles',$(this).val())
    });
    $("#add-category").on('change', function(e){
        setQuotaTableDefaults('#users-quota','categories',$(this).val())
    });
    $("#add-group").on('change', function(e){
        setQuotaTableDefaults('#users-quota','groups',$(this).val())
    });


    $("#edit-role").on('change', function(e){
         setQuotaTableDefaults('#edit-users-quota','roles',$(this).val())
    });
    $("#edit-category").on('change', function(e){
        setQuotaTableDefaults('#edit-users-quota','categories',$(this).val())
    });
    $("#edit-group").on('change', function(e){
        setQuotaTableDefaults('#edit-users-quota','groups',$(this).val())
    });


    $("#bulk-role").on('change', function(e){
         setQuotaTableDefaults('#bulkusers-quota','roles',$(this).val())
    });
    $("#bulk-category").on('change', function(e){
        setQuotaTableDefaults('#bulkusers-quota','categories',$(this).val())
    });
    $("#bulk-group").on('change', function(e){
        setQuotaTableDefaults('#bulkusers-quota','groups',$(this).val())
    });

            //~ $("input").click(function () {
                //~ console.log('in')
                //~ if($(this).prop("checked")){
                    //~ $(this).next('ul').find('input:checkbox').prop('checked', $(this).prop("checked")).prop('disabled',true);
                //~ }else{
                    //~ $(this).next('ul').find('input:checkbox').prop('checked', $(this).prop("checked")).prop('disabled',true);
                //~ }
            //~ });

    //~ $('#domains_tree input:checkbox').attr('disabled',true);
     $('#domains_tree input:checkbox').on('ifChecked', function(event){
         console.log('ifchecked')
        $(this).closest('div').next('ul').find('input:checkbox').iCheck('check').attr('disabled',true) //.prop('disabled',true);
     });
     $('#domains_tree input:checkbox').on('ifUnchecked', function(event){
         console.log('ifunchecked')
          $(this).closest('div').next('ul').find('input:checkbox').iCheck('uncheck').attr('disabled',false)
     });        
            
    table=$('#users').DataTable( {
        "ajax": {
            "url": "/admin/users/get/",
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
                                    if(type === "display"){
                                        if(full.active==true){
                                            return '<i class="fa fa-check" style="color:lightgreen"></i>';
                                        }else{
                                            return '<i class="fa fa-close" style="color:darkgray"></i>';
                                        }
                                    }
                                    return data;
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
            //~ row.child(false).remove()
            tr.removeClass('shown');
        }
        else {
            // Open this row
            row.child( renderUsersDetailPannel(row.data()) ).show();
            
            actionsUserDetail()
            //~ setQuotaOptions('#show-users-quota',true);
            //~ editData();
            tr.addClass('shown');
            setQuotaDataDefaults('#show-users-quota',row.data())
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

    socket.on('user_quota', function(data) {
        console.log('Quota update')
        var data = JSON.parse(data);
        drawUserQuota(data);
    });
    
    socket.on('add_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $('form').each(function() { this.reset() });
            $('.modal').modal('hide');
            
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
        table.ajax.reload()
    });

    socket.on ('result', function (data) {
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
        table.ajax.reload()
    });    
       
    //~ socket.on('user_quota', function(data) {
        //~ console.log('Quota update')
        //~ var data = JSON.parse(data);
        //~ drawUserQuota(data);
    //~ });
    
});

//~ function format ( d ) {
    //~ // `d` is the original data object for the row
    //~ var cells='<div class="btn-group"> \
                                //~ <button class="btn btn-sm btn-default btn-edit" id="btn-edit" type="button"  data-placement="top" data-toggle="tooltip" data-original-title="Edit"><i class="fa fa-pencil"></i></button> \
                              //~ </div>';
    //~ for(var k in d){
		//~ cells+='<tr>'+
					//~ '<td>'+k+':</td>'+
					//~ '<td>'+d[k]+'</td>'+
				//~ '</tr>'
	//~ }
    //~ return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">'+
        //~ cells+
    //~ '</table>';
//~ }

function actionsUserDetail(){
	$('.btn-edit').on('click', function () {
            setQuotaOptions('#edit-users-quota');
            var pk=$(this).closest("div").attr("data-pk");
            $("#modalEditUserForm")[0].reset();
			$('#modalEditUser').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            setModalUser()
            setQuotaTableDefaults('#edit-users-quota','users',pk)
            api.ajax('/admin/tabletest/users/post','POST',{'id':pk}).done(function(user) {
                $('#modalEditUserForm #name').val(user.name);
                $('#modalEditUserForm #id').val(user.id);
                $('#modalEditUserForm #mail').val(user.mail);
                $('#modalEditUserForm #role option:selected').prop("selected", false);
                $('#modalEditUserForm #role option[value="'+user.role+'"]').prop("selected",true);
                $('#modalEditUserForm #category option:selected').prop("selected", false);
                $('#modalEditUserForm #category option[value="'+user.category+'"]').prop("selected",true);
                $('#modalEditUserForm #group option:selected').prop("selected", false);
                $('#modalEditUserForm #group option[value="'+user.group+'"]').prop("selected",true);                
            });
             //~ $('#hardware-block').hide();
            //~ $('#modalEdit').parsley();
            //~ modal_edit_desktop_datatables(pk);
	});

	$('.btn-passwd').on('click', function () {
            //~ setQuotaOptions('#edit-users-quota');
            var closest=$(this).closest("div");
            var pk=closest.attr("data-pk");
            var name=closest.attr("data-name");
            //~ var user=closest.attr("data-user");
            $("#modalPasswdUserForm")[0].reset();
			$('#modalPasswdUser').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalPasswdUserForm #name').val(name);
            $('#modalPasswdUserForm #id').val(pk);
             //~ $('#hardware-block').hide();
            //~ $('#modalEdit').parsley();
            //~ modal_edit_desktop_datatables(pk);
	});

	//~ $('.btn-delete').on('click', function () {
            //~ // setQuotaOptions('#edit-users-quota');
            //~ var pk=$(this).closest("div").attr("data-pk");
            //~ // $("#modalDeleteUserForm")[0].reset();
			//~ $('#modalDeleteUserTree').modal({
				//~ backdrop: 'static',
				//~ keyboard: false
			//~ }).modal('show');
            //~ // GENERATE DOMAINS_TREE
            //~ api.ajax('/admin/user/delete','POST',{'pk':pk}).done(function(user) {console.log('done')})
            //~ $('#domains_tree input:checkbox').iCheck('check');
    //~ });
    
//~ <div id="domains_tree">
                    //~ <ul>
                        //~ <li>
                            //~ <input type="checkbox" />
                            //~ Root
                            //~ <ul>
                                //~ <li>
                                    //~ <input type="checkbox" />
                                    //~ Child 1
                                    //~ <ul>
                                        //~ <li>
                                            //~ <input type="checkbox
    

    
    
	$('.btn-delete').on('click', function () {
            // setQuotaOptions('#edit-users-quota');
            var pk=$(this).closest("div").attr("data-pk");
            $("#modalDeleteUserForm")[0].reset();
			$('#modalDeleteUser').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            // setModalUser()
            // setQuotaTableDefaults('#edit-users-quota','users',pk)
            api.ajax('/admin/user/delete','POST',{'pk':pk}).done(function(user) {
                $('.user-desktops').text(user.desktops.length);
                $('.user-templates').text(user.templates.length);
                $('.user-templates-ok').text(user.templates.length-user.risky_templates.length);
                $('.user-templates-ko').text(user.risky_templates.length);
                $('.user-templates-ko-count').text(user.others_domains);
                // $('#modalEditForm #name').val(user.name);
                // $('#modalEditForm #id').val(user.id);
                // $('#modalEditForm #mail').val(user.mail);
                // $('#modalEditForm #role option:selected').prop("selected", false);
                // $('#modalEditForm #role option[value="'+user.role+'"]').prop("selected",true);
                // $('#modalEditForm #category option:selected').prop("selected", false);
                // $('#modalEditForm #category option[value="'+user.category+'"]').prop("selected",true);
                // $('#modalEditForm #group option:selected').prop("selected", false);
                // $('#modalEditForm #group option[value="'+user.group+'"]').prop("selected",true);                
            });
             // $('#hardware-block').hide();
            // $('#modalEdit').parsley();
            // modal_edit_desktop_datatables(pk);
	});


		$('.btn-active').on('click', function () {
                var closest=$(this).closest("div");
				var pk=closest.attr("data-pk");
				var name=closest.attr("data-name");
                new PNotify({
						title: 'Confirmation Needed',
							text: "Are you sure you want to enable/disable: "+name+"?",
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
							addclass: 'pnotify-center'
						}).get().on('pnotify.confirm', function() {
                            socket.emit('user_toggle',{'pk':pk,'name':name})
						}).on('pnotify.cancel', function() {
                    });	
                });
        
}

function modal_edit_user(id){
    
	$.ajax({
		type: "GET",
		url:"/desktops/templateUpdate/" + id,
		success: function(data)
		{
            $('#modalEditDesktop #forced_hyp').closest("div").remove();
			$('#modalEditDesktop #name_hidden').val(data.name);
            $('#modalEditDesktop #name').val(data.name);
			$('#modalEditDesktop #description').val(data.description);
            $('#modalEditDesktop #id').val(data.id);
            setHardwareDomainDefaults('#modalEditDesktop', id);
		}				
	});
  
    
}

function renderUsersDetailPannel ( d ) {
		$newPanel = $template.clone();
		$newPanel.html(function(i, oldHtml){
			return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name);
		});
		return $newPanel
}

    function setModalUser(){
        api.ajax_async('/admin/userschema','POST','').done(function(d) {
            $.each(d, function(key, value) {
                    $("." + key).find('option').remove().end();
                    for(var i in d[key]){
                        if(value[i].id!='disposables' && value[i].id!='eval'){
                            $("."+key).append('<option value=' + value[i].id + '>' + value[i].name + '</option>');
                            //~ if(value[i].id=='local'){
                                //~ $("."+key+' option[value="'+value[i]+'"]').prop("selected",true);
                            //~ }
                        }
                    }
                    $("."+key+' option[value="local"]').prop("selected",true);
            });
                
        });       
    }

function populate_users_table(){
        olduserstable=$('#oldusers_table').DataTable( {
			"ajax": {
				"url": "/admin/users/nonexists/",
                "contentType": "application/json",
                "type": 'POST',
                "data": function(d){return JSON.stringify({})}
			},
            "sAjaxDataProp": "",
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
            "bLengthChange": false,
            "bFilter": false,
			"rowId": "id",
			"deferRender": true,
			"columns": [
                { "data": "id", "width": "88px"},
                { "data": "name"},
                { "data": "accessed", "width": "88px"},
                ],
             "order": [[0, 'asc']],
             "columnDefs": [ ]
        } );

    $('.btn-disable-olds').on( 'click', function () {
				new PNotify({
						title: 'Disable all this users',
							text: "Do you really want to disable all this users? (they don't exists on your LDAP)",
							hide: false,
							opacity: 0.9,
							confirm: {confirm: true},
							buttons: {closer: false,sticker: false},
							history: {history: false},
							addclass: 'pnotify-center'
						}).get().on('pnotify.confirm', function() {
                            api.ajax('/admin/users/nonexists','POST',{'commit':true}).done(function(data) {
                                            $("#modalOldUsers").modal('hide');
                                            table.ajax.reload();
                            });  
						}).on('pnotify.cancel', function() {
				});	         
    });        
        


        
}
