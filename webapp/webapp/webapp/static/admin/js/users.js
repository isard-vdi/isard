/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var users_table= ''
$(document).ready(function() {
    $('.admin-status').show()
    $template = $(".template-detail-users");
    
	$('.btn-new-user').on('click', function () {
        setQuotaMax('#users-quota',kind='category',id=false,disabled=false);
        $('#modalAddUser').modal({backdrop: 'static', keyboard: false}).modal('show');
        $('#modalAddUserForm')[0].reset();
        setModalUser();
	});


    
	$('.btn-new-bulkusers').on('click', function () {
        setQuotaMax('#bulkusers-quota',kind='category',id=false,disabled=false);
        $('#modalAddBulkUsers').modal({backdrop: 'static', keyboard: false}).modal('show');
        $('#modalAddBulkUsersForm')[0].reset();
        setModalUser();
	});

	$('#btn-download-bulkusers').on('click', function () {
        var viewerFile = new Blob(["username,name,email,password\njdoe,John Doe,jdoe@isardvdi.com,sup3rs3cr3t\nauser,Another User,auser@domain.com,a1sera1ser"], {type: "text/csv"});
        var a = document.createElement('a');
            a.download = 'bulk-users-template.csv';
            a.href = window.URL.createObjectURL(viewerFile);
        var ev = document.createEvent("MouseEvents");
            ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
            a.dispatchEvent(ev);  
	});

    function filter_groups(category_select, group_select) {
        let category = category_select.val()
        group_select.find('option').each(function () {
            if (this.value.startsWith(category + "-")) {
                this.disabled = false
            } else {
                this.disabled = true
                if (this.selected) {
                    $(this).prop('selected', false)
                }
            }
        })
    }
    $("#add-category").on('change', function () {
        filter_groups($(this), $('#add-group'))
    })
    $("#bulk-category").on('change', function () {
        filter_groups($(this), $('#bulk-group'))
    })

    $("#modalAddUser #send").on('click', function(e){
        var form = $('#modalAddUserForm');
        formdata = form.serializeObject()
        form.parsley().validate();
        if (form.parsley().isValid()){   // || 'unlimited' in formdata){   
            data=userQuota2dict(formdata);
            data['password']=data['password-add-user'];
            delete data['password-add-user'];
            delete data['password2-add-user'];
            delete data['unlimited'];
            data['id']=data['username']=$('#modalAddUserForm #id').val();                     
            socket.emit('user_add',data);
        }
    }); 

    $("#modalEditUser #send").on('click', function(e){
        var form = $('#modalEditUserForm');
        formdata = form.serializeObject()
        form.parsley().validate();
        if (form.parsley().isValid()){     // || 'unlimited' in formdata){   
            data=userQuota2dict(formdata);
            delete data['unlimited']
            //data['id']=$('#modalEditUserForm #id').val();
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
            data['password']=$('#modalPasswdUserForm #password-reset').val();
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
            
    $("#modalDeleteUser #send").on('click', function(e){
        id=$('#modalDeleteUserForm #id').val();
        socket.emit('user_delete',id)
     }); 

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
        formdata = form.serializeObject()
        form.parsley().validate();
        if (form.parsley().isValid()){     // || 'unlimited' in formdata){   
            data=userQuota2dict(formdata);
            delete data['unlimited']
            users=parseCSV()
            socket.emit('bulkusers_add',{'data':data,'users':users})
            $('#modalAddBulkUsers #send').prop('disabled', true);
        }
    }); 


    var form = $('#modalEditUserForm');
    formdata = form.serializeObject()
    form.parsley().validate();
    if (form.parsley().isValid()){              // || 'unlimited' in formdata){   
        data=userQuota2dict(formdata);
        delete data['unlimited']
        //data['id']=$('#modalEditUserForm #id').val();
        socket.emit('user_edit',data)
    }


    $("#add-category").on('change', function(e){
        setQuotaMax('#users-quota',kind='category',id=$(this).val(),disabled=false);
        //setQuotaTableDefaults('#users-quota','categories',$(this).val())
    });
    $("#add-group").on('change', function(e){
        setQuotaMax('#users-quota',kind='group',id=$(this).val(),disabled=false);
        //setQuotaTableDefaults('#users-quota','groups',$(this).val())
    });

    $("#bulk-category").on('change', function(e){
        setQuotaMax('#bulkusers-quota',kind='category',id=$(this).val(),disabled=false);
        /* setQuotaTableDefaults('#bulkusers-quota','categories',$(this).val()) */
    });
    $("#bulk-group").on('change', function(e){
        setQuotaMax('#bulkusers-quota',kind='group',id=$(this).val(),disabled=false);
        /* setQuotaTableDefaults('#bulkusers-quota','groups',$(this).val()) */
    });


     $('#domains_tree input:checkbox').on('ifChecked', function(event){
        $(this).closest('div').next('ul').find('input:checkbox').iCheck('check').attr('disabled',true) //.prop('disabled',true);
     });
     $('#domains_tree input:checkbox').on('ifUnchecked', function(event){
          $(this).closest('div').next('ul').find('input:checkbox').iCheck('uncheck').attr('disabled',false)
     });        
            
    users_table=$('#users').DataTable( {
        "ajax": {
            "url": "/admin/users",
            "dataSrc": "",
            "type" : "GET",
            "data": function(d){return JSON.stringify({})}
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
            { "data": "name"},
            { "data": "provider"},
            { "data": "category"},
            { "data": "uid"},
            { "data": "username"},
            { "data": "role", "width": "10px"},
            { "data": "group", "width": "10px"},
            { "data": "vpn.wireguard.connected", "width": "10px", "defaultContent": 'NaN'},
            //~ {
                //~ "data": null,
                //~ className: "center xe-password",
                //~ "defaultContent": '  \
                                //~ <div><i class="fa fa-lock"></i> \
                              //~ </div>'
            //~ },
            { "data": "accessed"},
            { "data": "templates", "width": "10px"},
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
                            "targets": 9,
                            "render": function ( data, type, full, meta ) {
                                if('vpn' in full && full['vpn']['wireguard']['connected']){
                                    return '<i class="fa fa-circle" aria-hidden="true"  style="color:green" title="'+full["vpn"]["wireguard"]["remote_ip"]+':'+full["vpn"]["wireguard"]["remote_port"]+'"></i>'
                                }else{
                                    return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                                }
                            }},
							{
							"targets":10,
							"render": function ( data, type, full, meta ) {
                                        return moment.unix(full.accessed).toISOString("YYYY-MM-DDTHH:mm:ssZ"); //moment.unix(full.accessed).fromNow();
                                        }}
             ]
        });
    //~ });

    $('#users').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = users_table.row( tr );

        if ( row.child.isShown() ) {
            row.child.hide();
            tr.removeClass('shown');
        }else {
            if ( users_table.row( '.shown' ).length ) {
                $('.details-control', users_table.row( '.shown' ).node()).click();
            }
            row.child(renderUsersDetailPannel(row.data())).show()
            actionsUserDetail()
            tr.addClass('shown');
            id = row.data().id
            setQuotaMax(
                '#show-users-quota-' + id,
                kind='user',
                id=id,
                disabled=true
            )
            setLimitsMax(
                '#show-users-limits-' + id,
                kind='user',
                id=id,
                disabled=true
            )
        }
    });



    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/isard-admin/sio_admins', {
        'path': '/isard-admin/socket.io/',
        'transports': ['websocket']
    });
     
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

    socket.on('users_data', function(data) {
        console.log('User update')
        users_table.ajax.reload()
        //var data = JSON.parse(data);
        //drawUserQuota(data);
    });

    socket.on('users_delete', function(data) {
        console.log('User update')
        users_table.ajax.reload()
        //var data = JSON.parse(data);
        //drawUserQuota(data);
    });

    socket.on('add_form_result', function (data) {
        var data = JSON.parse(data);
        //if(data.result){
            $('form').each(function() { this.reset() });
            $('.modal').modal('hide');
            $('#modalAddBulkUsers #send').prop('disabled', false);
        //}
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
        users_table.ajax.reload()
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
        users_table.ajax.reload()
    });    
    
});


function actionsUserDetail(){
	$('.btn-edit').on('click', function () {            
            var pk=$(this).closest("div").attr("data-pk");
            $("#modalEditUserForm")[0].reset();
			$('#modalEditUser').modal({
				backdrop: 'static',
				keyboard: false
            }).modal('show');
            setModalUser()
            api.ajax('/isard-admin/admin/load/users/post','POST',{'id':pk}).done(function(user) {
                $('#modalEditUserForm #name').val(user.name);
                $('#modalEditUserForm #id').val(user.id);
                $('#modalEditUserForm #uid').val(user.uid);
                $('#modalEditUserForm #email').val(user.email);
                $('#modalEditUserForm #role option:selected').prop("selected", false);
                $('#modalEditUserForm #role option[value="'+user.role+'"]').prop("selected",true);
                $('#modalEditUserForm #category option:selected').prop("selected", false);
                $('#modalEditUserForm #category option[value="'+user.category+'"]').prop("selected",true);
                $('#modalEditUserForm #group option:selected').prop("selected", false);
                $('#modalEditUserForm #group option[value="'+user.group+'"]').prop("selected",true);                
                $('#modalEditUserForm').parsley().validate();
            });
            setQuotaMax('#edit-users-quota',kind='user',id=pk,disabled=false);
	});

	$('.btn-passwd').on('click', function () {
            var closest=$(this).closest("div");
            var pk=closest.attr("data-pk");
            var name=closest.attr("data-name");
            var username=closest.attr("data-username");
            $("#modalPasswdUserForm")[0].reset();
			$('#modalPasswdUser').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalPasswdUserForm #name').val(name);
            $('#modalPasswdUserForm #id').val(pk);
            $('#modalPasswdUserForm #username').val(username);
	});

    
	$('.btn-delete').on('click', function () {
            var pk=$(this).closest("div").attr("data-pk");
            $("#modalDeleteUserForm")[0].reset();
            $('#modalDeleteUserForm #id').val(pk);
			$('#modalDeleteUser').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            api.ajax('/isard-admin/admin/user/delete','POST',{'pk':pk}).done(function(domains) {
                $('#table_modal_delete tbody').empty()
                $.each(domains, function(key, value) {
                    $('#table_modal_delete tbody').append('<tr>\
                                <th>'+value['kind']+'</th>\
                                <th>'+value['user']+'</th>\
                                <th>'+value['name']+'</th>\
								</tr>');
                });  
            });
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
		url:"/isard-admin/desktops/templateUpdate/" + id,
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
    if(d.id == 'local-default-admin-admin'){
        $('.template-detail-users .btn-delete').hide()
    }else{
        $('.template-detail-users .btn-delete').show()
    }

		$newPanel = $template.clone();
		$newPanel.html(function(i, oldHtml){
			return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.username/g, d.username);
        });
		return $newPanel
}

function setModalUser(){
    api.ajax_async('/isard-admin/admin/userschema','POST','').done(function(d) {
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
        $('#add-category').trigger("change")
    });       
}
