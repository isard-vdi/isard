/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$(document).ready(function() {
    $template_group = $(".template-detail-groups");
    var groups_table=$('#groups').DataTable( {
        "ajax": {
            "url": "/admin/table/groups",
            "dataSrc": "",
            "type" : "POST",
            "data": function(d){return JSON.stringify({})}
        },
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "columns": [
            {
            "className":      'details-show',
            "orderable":      false,
            "data":           null,
            "width": "10px",
            "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "name", className: "xe-name" },
            { "data": "description", className: "xe-description" },
            { "data": "limits.users", className: "xe-description", defaultContent: "-" },

            { "data": "quota.desktops", className: "xe-desktops", defaultContent: "-"},
            { "data": "limits.desktops", className: "xe-desktops", defaultContent: "-"},
            { "data": "quota.running", className: "xe-running", defaultContent: "-"},
            { "data": "limits.running", className: "xe-running", defaultContent: "-"},
            { "data": "quota.vcpus", className: "xe-vcpu", defaultContent: "-"},
            { "data": "limits.vcpus", className: "xe-vcpu", defaultContent: "-"},
            { "data": "quota.memory", className: "xe-memory", defaultContent: "-"},
            { "data": "limits.memory", className: "xe-memory", defaultContent: "-"},
            { "data": "quota.templates", className: "xe-templates", defaultContent: "-"},
            { "data": "limits.templates", className: "xe-templates", defaultContent: "-"},
            { "data": "quota.isos", className: "xe-isos", defaultContent: "-"},
            { "data": "limits.isos", className: "xe-isos", defaultContent: "-"},
        ]
    } );

    $('#groups').find('tbody').on('click', 'td.details-show', function () {
        var tr = $(this).closest('tr');
        var row = groups_table.row( tr );
 
        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            if ( groups_table.row( '.shown' ).length ) {
                $('.details-show', groups_table.row( '.shown' ).node()).click();
            }
            row.child( renderGroupsDetailPannel(row.data()) ).show();
            actionsGroupDetail()
            tr.addClass('shown');
            //setQuotaMax('.show-groups-quota-'+row.data().id,kind='group',id=row.data().id,disabled=true);
            //setLimitsMax('.show-groups-limits-'+row.data().id,kind='group',id=row.data().id,disabled=true);            
        }
    });



    socket.on('groups_data', function (data) {
        groups_table.ajax.reload()
    });

    socket.on('groups_delete', function (data) {
        groups_table.ajax.reload()
    });

    $("#modalDeleteGroup #send").on('click', function(e){
        id=$('#modalDeleteGroupForm #id').val();

        var notice = new PNotify({
            text: 'Deleting group...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        $('form').each(function() { this.reset() });
        $('.modal').modal('hide');
        $.ajax({
            type: "DELETE",
            url:"/api/v3/admin/group/"+id ,
            contentType: "application/json",
            error: function(data) {
                notice.update({
                    title: 'ERROR',
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            },
            success: function(data)
            {
                notice.update({
                    text: 'Group deleted successfully',
                    hide: true,
                    delay: 2000,
                    icon: '',
                    opacity: 1,
                    type: 'success'
                })
            }
        });
        }); 

	$('.btn-new-group').on('click', function () {
        //setQuotaMax('#roles-quota');
			$('#modalAddGroup').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            removeError($('#modalAddGroup'))
            $('#modalAddGroupForm')[0].reset();

            $('#modalAddGroupForm #linked_groups').select2({
                minimumInputLength: 2,
                multiple: true,
                ajax: {
                    type: "POST",
                    url: '/api/v3/admin/alloweds/term/groups/',
                    dataType: 'json',
                    contentType: "application/json",
                    delay: 250,
                    data: function (params) {
                        return  JSON.stringify({
                            term: params.term,
                        });
                    },
                    processResults: function (data) {
                        return {
                            results: $.map(data, function (item, i) {
                                return {
                                    text: item.name,
                                    id: item.id
                                }
                            })
                        };
                    }
                },
            });   
    

            //~ setModalAddUser();

            api.ajax_async('/api/v3/admin/userschema','POST','').done(function(d) {
                $.each(d, function(key, value) {
                    if(key == 'category'){
                        $("#parent_category").find('option').remove().end();
                        for(var i in d[key]){
                            $("#parent_category").append('<option value=' + value[i].id + '>' + value[i].name + ' - ' + value[i].description + '</option>');
                        }
                        //$("."+key+' option[value="local"]').prop("selected",true);
                    }
                });   
            }); 

             $('#modalAddGroupForm #auto-desktops').select2({
                minimumInputLength: 2,
                multiple: true,
                ajax: {
                    type: "GET",
                    url: '/api/v3/user/templates/allowed/all',
                    dataType: 'json',
                    contentType: "application/json",
                    delay: 250,
                    data: function (params) {
                        return  JSON.stringify({
                            term: params.term,
                            pluck: ['id','name']
                        });
                    },
                    processResults: function (data) {
                        return {
                            results: $.map(data, function (item, i) {
                                return {
                                    text: item.name,
                                    id: item.id
                                }
                            })
                        };
                    }
                },
            });   
		
        $("#modalAddGroupForm #ephimeral-minutes").ionRangeSlider({
                  type: "single",
                  min: 5,
                  max: 120,
                  step:5,
                  grid: true,
                  disable: false
                  }).data("ionRangeSlider").update();
                  
        $("#modalAddGroupForm #ephimeral-enabled").on('ifChecked', function(event){
				  $("#modalAddGroupForm #ephimeral-data").show();
		});
        $("#modalAddGroupForm #ephimeral-enabled").on('ifUnchecked', function(event){
				  $("#modalAddGroupForm #ephimeral-data").hide();
		});        

        $("#modalAddGroupForm #auto-desktops-enabled").on('ifChecked', function(event){
				  $("#modalAddGroupForm #auto-desktops-data").show();
		});
        $("#modalAddGroupForm #auto-desktops-enabled").on('ifUnchecked', function(event){
				  $("#modalAddGroupForm #auto-desktops-data").hide();
		});            
	});    


                          
    $("#modalAddGroup #send").on('click', function(e){
            var form = $('#modalAddGroupForm');
            form.parsley().validate();
            if (form.parsley().isValid()){
                data=$('#modalAddGroupForm').serializeObject();
                data = form.serializeObject();
                if(!data['ephimeral-enabled']){
                    delete data['ephimeral-minutes'];
                    delete data['ephimeral-action'];
                }else{
                    delete data['ephimeral-enabled'];
                    data['ephimeral-minutes'] = parseInt(data['ephimeral-minutes'])
                }
                delete data['ephimeral-enabled'];
                delete data['auto-desktops-enabled'];
                data=JSON.unflatten(data);
                var notice = new PNotify({
                    text: 'Creating group...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({ 
                    type: "POST",
                    url:"/api/v3/admin/group",
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function(data)
                    {
                        $('form').each(function() { this.reset() });
                        $('.modal').modal('hide');
                        notice.update({
                            title: "Created",
                            text: 'Group created successfully',
                            hide: true,
                            delay: 2000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                    },
                    error: function (data) {
                        notice.update({
                            title: 'ERROR',
                            text: "Couldn't create group",
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        })
                    }

                });  
            }
        });     
    
});

function renderGroupsDetailPannel ( d ) {
    $newPanel = $template_group.clone();
    $newPanel.html(function(i, oldHtml){
        var linked_groups_names = []
            $.each(d.linked_groups_data, function(i, group) {
                linked_groups_names.push(group.name)
            })
        return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description).replace(/d.linked_groups/g, linked_groups_names);
    });
    return $newPanel
}


function actionsGroupDetail(){
    $('.btn-edit-quotas').off('click').on('click', function () {
        var pk=$(this).closest("div").attr("data-pk");

        $("#modalEditQuotaForm")[0].reset();
        $("#modalEditQuotaForm #propagate").removeAttr('checked').iCheck('update')
        $('#modalEditQuotaForm #id').val(pk);
        $('#modalEditQuota').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        setQuotaMax('#modalEditQuotaForm',kind='group',id=pk,disabled=false);        
	});

    $("#modalEditQuota #send").off('click').on('click', function(e){
        form = $('#modalEditQuotaForm')
        pk=$('#modalEditQuotaForm #id').val();
        form.parsley().validate();
        formdata=form.serializeObject()
        if (form.parsley().isValid() || 'unlimited' in formdata){
            if('unlimited' in formdata){
                dataform={}
                dataform['quota']=false
            }else{
                dataform=quota2dict(formdata)
            } 
            data={}
            data['quota']=dataform['quota']
            if('propagate' in formdata){
                data['propagate']=true;
            }
            var notice = new PNotify({
                text: 'Updating quota...',
                hide: false,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })
    
            $.ajax({
                type: "PUT",
                url:"/api/v3/admin/quota/group/"+pk ,
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function(data)
                {
                    $('form').each(function() { this.reset() });
                    $('.modal').modal('hide');
                    notice.update({
                        text: 'Quota updated successfully',
                        hide: true,
                        delay: 1000,
                        icon: 'fa fa-' + data.icon,
                        opacity: 1,
                        type: 'success'
                    })
                },
                error: function(data) {
                    notice.update({
                        title: 'ERROR',
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 2000,
                        opacity: 1
                    })
                },
    
            });
        }
    });

    $('.btn-edit-limits').off('click').on('click', function () {
        var pk=$(this).closest("div").attr("data-pk");
        $("#modalEditLimitsForm")[0].reset();
        $('#modalEditLimitsForm #id').val(pk);
        $("#modalEditLimitsForm #propagate").removeAttr('checked').iCheck('update')
        $('#modalEditLimits').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        setLimitsMax('#modalEditLimitsForm',kind='group',id=pk,disabled=false);         
    });

    $("#modalEditLimits #send").off('click').on('click', function(e){
        form = $('#modalEditLimitsForm')
        pk=$('#modalEditLimitsForm #id').val();

        form.parsley().validate();
        formdata=form.serializeObject()        
        if (form.parsley().isValid() || 'unlimited' in formdata){
            if('unlimited' in formdata){
                dataform={}
                dataform['limits']=false
            }else{
                dataform=quota2dict(form.serializeObject())
            }
            data={}
            data['limits']=dataform['limits']
            if('propagate' in formdata){
                data['propagate']=true;
            }
            var notice = new PNotify({
                text: 'Updating limits...',
                hide: false,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })
            $.ajax({
                type: "PUT",
                url:"/api/v3/admin/limits/group/"+pk ,
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function(data)
                {
                    $('form').each(function() { this.reset() });
                    $('.modal').modal('hide');
                    notice.update({
                        text: 'Limits updated successfully',
                        hide: true,
                        delay: 1000,
                        icon: 'fa fa-' + data.icon,
                        opacity: 1,
                        type: 'success'
                    })
                },
                error: function(data) {
                    notice.update({
                        title: 'ERROR',
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 2000,
                        opacity: 1
                    })
                },
            });  
        }
    });

	$('.btn-delete').on('click', function () {
        var pk=$(this).closest("div").attr("data-pk");
        var data = {
            'id': pk,
            'table': 'group'
        }

        $("#modalDeleteGroupForm")[0].reset();
        $('#modalDeleteGroupForm #id').val(pk);
        $('#modalDeleteGroup').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        // setModalUser()
        // setQuotaTableDefaults('#edit-users-quota','users',pk) 
        $.ajax({
            type: "POST",
            url: "/api/v3/admin/delete/check",
            data: JSON.stringify(data),
            contentType: "application/json"
        }).done(function(domains) {
            $('#table_modal_group_delete tbody').empty()
            $.each(domains, function(key, value) {
                infoDomains(value, $('#table_modal_group_delete tbody'));
            });  
        });
    });

$('.btn-enrollment').on('click', function () {
    var pk=$(this).closest("div").attr("data-pk");
        $("#modalEnrollmentForm")[0].reset();
        $('#modalEnrollmentForm #id').val(pk);
        $('#modalEnrollment').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        data={}
        data['id']=pk;
        // setModalUser()
        $.ajax({
            type: 'POST',
            url: '/api/v3/admin/table/groups',
            data: JSON.stringify(data)
        }).done(function(data) {
            if(data.enrollment.manager != false){
                $('#manager-key').show();
                $('.btn-copy-manager').show();
                $('#manager-key').val('test');
                $('#manager-check').iCheck('check');
                $('#manager-key').val(data.enrollment.manager);
            }else{
                // https://github.com/dargullin/icheck/issues/159
                $('#manager-check').iCheck('uncheck').iCheck('update');
                $('#manager-key').hide();
                $('.btn-copy-manager').hide();
            }
            if(data.enrollment.advanced != false){
                $('#advanced-key').show();
                $('.btn-copy-advanced').show();
                $('#advanced-key').val('test');
                $('#advanced-check').iCheck('check');
                $('#advanced-key').val(data.enrollment.advanced);
            }else{
                // https://github.com/dargullin/icheck/issues/159
                $('#advanced-check').iCheck('uncheck').iCheck('update');
                $('#advanced-key').hide();
                $('.btn-copy-advanced').hide();
            }
            if(data.enrollment.user != false){
                $('#user-key').show();
                $('.btn-copy-user').show();
                $('#user-key').val('test');
                $('#user-check').iCheck('check');
                $('#user-key').val(data.enrollment.user);
            }else{
                // https://github.com/dargullin/icheck/issues/159
                $('#user-check').iCheck('uncheck').iCheck('update');
                $('#user-key').hide();
                $('.btn-copy-user').hide();
            }
        }); 
    });

    $('#manager-check').unbind('ifChecked').on('ifChecked', function(event){
        if($('#manager-key').val()==''){
            pk=$('#modalEnrollmentForm #id').val();
            data['role']="manager";
            data['action']="reset";
            $.ajax({
                type: "POST",
                data: JSON.stringify(data),
                url:"/api/v3/admin/group/enrollment",
                contentType: "application/json",
                success: function(data)
                {
                    $('#manager-key').val(data);
                }
                });         
            $('#manager-key').show();
            $('.btn-copy-manager').show();
        }
      }); 
    $('#manager-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
        pk=$('#modalEnrollmentForm #id').val();
        data['role']="manager";
        data['action']="disable";
        new PNotify({
            title: 'Confirmation Needed',
                text: "Are you sure you want to delete manager code?",
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
                pk=$('#modalEnrollmentForm #id').val();
            $.ajax({
                type: "POST",
                data: JSON.stringify(data),
                url:"/api/v3/admin/group/enrollment",
                contentType: "application/json",
                success: function(data)
            {
                $('#manager-key').val('');
            }
            })     
                $('#manager-key').hide();
                $('.btn-copy-manager').hide();
            }).on('pnotify.cancel', function() {
                console.log('cancel')
                $('#manager-check').iCheck('check');
                $('#manager-key').show();
                $('.btn-copy-manager').show();
            });
        }); 

        $('#advanced-check').unbind('ifChecked').on('ifChecked', function(event){
            if($('#advanced-key').val()==''){
                pk=$('#modalEnrollmentForm #id').val();
                data['role']="advanced";
                data['action']="reset";
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/group/enrollment",
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function(data)
                    {
                        $('#advanced-key').val(data);
                    }
                    }); 
                $('#advanced-key').show();
                $('.btn-copy-advanced').show();
            }
          }); 
        $('#advanced-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
            pk=$('#modalEnrollmentForm #id').val();
            data['role']="advanced";
            data['action']="disable";
            new PNotify({
                title: 'Confirmation Needed',
                    text: "Are you sure you want to delete advanced code?",
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
                    pk=$('#modalEnrollmentForm #id').val();
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/group/enrollment",
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function(data)
                    {
                        $('#advanced-key').val('');
                    }
                    })              
                    $('#advanced-key').hide();
                    $('.btn-copy-advanced').hide();
                }).on('pnotify.cancel', function() {
                    console.log('cancel')
                    $('#advanced-check').iCheck('check');
                    $('#advanced-key').show();
                    $('.btn-copy-advanced').show();
                });
            });
            
            $('#user-check').unbind('ifChecked').on('ifChecked', function(event){
                if($('#user-key').val()==''){
                    pk=$('#modalEnrollmentForm #id').val();
                    data['role']="user";
                    data['action']="reset";
                    $.ajax({
                        type: "POST",
                        url:"/api/v3/admin/group/enrollment",
                        data: JSON.stringify(data),
                        contentType: "application/json",
                        success: function(data)
                        {
                            $('#user-key').val(data);
                        }
                        });      
                    $('#user-key').show();
                    $('.btn-copy-user').show();
                }
              }); 
            $('#user-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
                pk=$('#modalEnrollmentForm #id').val();
                data['role']="user";
                data['action']="disable";
                new PNotify({
                    title: 'Confirmation Needed',
                        text: "Are you sure you want to delete user code?",
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
                        pk=$('#modalEnrollmentForm #id').val();
                        $.ajax({
                            type: "POST",
                            url:"/api/v3/admin/group/enrollment",
                            data: JSON.stringify(data),
                            contentType: "application/json",
                            success: function(data)
                            {
                                $('#user-key').val('');
                            }
                        })         
                        $('#user-key').hide();
                        $('.btn-copy-user').hide();
                    }).on('pnotify.cancel', function() {
                        console.log('cancel')
                        $('#user-check').iCheck('check');
                        $('#user-key').show();
                        $('.btn-copy-user').show();
                    });
                });            

    $('.btn-copy-manager').on('click', function () {
        $('#manager-key').prop('disabled',false).select().prop('disabled',true);
        document.execCommand("copy");
    });
    $('.btn-copy-advanced').on('click', function () {
        $('#advanced-key').prop('disabled',false).select().prop('disabled',true);
        document.execCommand("copy");
    });
    $('.btn-copy-user').on('click', function () {
        $('#user-key').prop('disabled',false).select().prop('disabled',true);
        document.execCommand("copy");
    });            
}
