/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

//var categories_table = ''
$(document).ready(function() {
    $template_category = $(".template-detail-categories");
    var categories_table=$('#categories').DataTable( {
        "ajax": {
            "url": "/isard-admin/admin/table/categories/get",
            "dataSrc": ""
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
            { "data": "limits-users", className: "xe-description", defaultContent: "-" },

            { "data": "quota-desktops", className: "xe-desktops", defaultContent: "-"},
            { "data": "limits-desktops", className: "xe-desktops", defaultContent: "-"},
            { "data": "quota-running", className: "xe-running", defaultContent: "-"},
            { "data": "limits-running", className: "xe-running", defaultContent: "-"},
            { "data": "quota-vcpus", className: "xe-vcpu", defaultContent: "-"},
            { "data": "limits-vcpus", className: "xe-vcpu", defaultContent: "-"},
            { "data": "quota-memory", className: "xe-memory", defaultContent: "-"},
            { "data": "limits-memory", className: "xe-memory", defaultContent: "-"},
            { "data": "quota-templates", className: "xe-templates", defaultContent: "-"},
            { "data": "limits-templates", className: "xe-templates", defaultContent: "-"},
            { "data": "quota-isos", className: "xe-isos", defaultContent: "-"},
            { "data": "limits-isos", className: "xe-isos", defaultContent: "-"},            
        ],
        "columnDefs": [
            {
            "targets": 0,
            "render": function ( data, type, full, meta ) {
                if('editable' in full){
                    if(full.editable == false){
                        return ''
                    }
                }
                return data;
                }
            }, 
        ]
    } );

    $('#categories').find('tbody').on('click', 'td.details-show', function () {
        var tr = $(this).closest('tr');
        var row = categories_table.row( tr );
 
        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            if ( categories_table.row( '.shown' ).length ) {
                $('.details-show', categories_table.row( '.shown' ).node()).click();
            }
            row.child( renderCategoriesDetailPannel(row.data()) ).show();
            actionsCategoryDetail();
            tr.addClass('shown');
            //setQuotaMax('.show-categories-quota-'+row.data().id,kind='category',id=row.data().id,disabled=true);
            //setLimitsMax('.show-categories-limits-'+row.data().id,kind='category',id=row.data().id,disabled=true);            
        }
    } );

    socket.on('categories_data', function (data) {
        categories_table.ajax.reload()
        console.log('form_result')
        socket.emit('user_quota','')        
    });

    socket.on('categories_delete', function (data) {
        categories_table.ajax.reload()
    });

    $("#modalDeleteCategory #send").on('click', function(e){
        id=$('#modalDeleteCategoryForm #id').val();
        socket.emit('category_delete',id)
        }); 

	$('.btn-new-category').on('click', function () {
        //setQuotaMax('#categories-quota');
			$('#modalAddCategory').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalAddCategoryForm')[0].reset();
            //~ setModalAddUser();
            
             $('#modalAddCategoryForm #auto-desktops').select2({
                minimumInputLength: 2,
                multiple: true,
                ajax: {
                    type: "POST",
                    url: '/isard-admin/admin/getAllTemplates',
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
		
        $("#modalAddCategoryForm #ephimeral-minutes").ionRangeSlider({
                  type: "single",
                  min: 5,
                  max: 120,
                  step:5,
                  grid: true,
                  disable: false
                  }).data("ionRangeSlider").update();
                  
        $("#modalAddCategoryForm #ephimeral-enabled").on('ifChecked', function(event){
				  $("#modalAddCategoryForm #ephimeral-data").show();
		});
        $("#modalAddCategoryForm #ephimeral-enabled").on('ifUnchecked', function(event){
				  $("#modalAddCategoryForm #ephimeral-data").hide();
		});        

        $("#modalAddCategoryForm #auto-desktops-enabled").on('ifChecked', function(event){
				  $("#modalAddCategoryForm #auto-desktops-data").show();
		});
        $("#modalAddCategoryForm #auto-desktops-enabled").on('ifUnchecked', function(event){
				  $("#modalAddCategoryForm #auto-desktops-data").hide();
        });
                
	});    

    $("#modalAddCategory #send").on('click', function(e){
            var form = $('#modalAddCategoryForm');

            form.parsley().validate();
            if (form.parsley().isValid()){
                data=$('#modalAddCategoryForm').serializeObject();
                if('frontend' in data){
                    data['frontend']=true
                }
                if(!('ephimeral-enabled' in data)){
                    delete data['ephimeral-minutes'];
                    delete data['ephimeral-action'];
                }
                if(!('auto-desktops-enabled' in data)){
                    delete data['auto-desktops'];
                }
                data['table']='categories';
                socket.emit('role_category_group_add',data)  
            }
        });  
        


});



function renderCategoriesDetailPannel ( d ) {
    if(d.editable == false){
        $('.template-detail-categories .btn-delete').hide()
        $('.template-detail-categories .btn-edit-quotas').hide()
        $('.template-detail-categories .btn-edit-limits').hide()
    }else{
        $('.template-detail-categories .btn-delete').show()
        $('.template-detail-categories .btn-edit-quotas').show()
        $('.template-detail-categories .btn-edit-limits').show()
    }    
    if(d.id == "default"){$('.template-detail-categories .btn-delete').hide()}
    $newPanel = $template_category.clone();
    $newPanel.html(function(i, oldHtml){
        return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name);
    });
    return $newPanel
}


function actionsCategoryDetail(){
    $('.btn-edit-category').unbind().on('click', function () {
        var pk=$(this).closest("div").attr("data-pk");

        $("#modalEditCategoryForm")[0].reset();
        $("#modalEditCategoryForm #auto-desktops").select2({
            minimumInputLength: 2,
            multiple: true,
            ajax: {
                type: "POST",
                url: '/isard-admin/admin/getAllTemplates',
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
        $('#modalEditCategoryForm #id').val(pk);
        $('#modalEditCategory').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        api.ajax('/isard-admin/admin/load/categories/post','POST',{'id':pk}).done(function(category) {
            $('#modalEditCategoryForm #name').val(category.name);
            $('#modalEditCategoryForm #description').val(category.description);
            $('#modalEditCategoryForm #id').val(category.id);

            if(category['frontend'] == true){
                $('#modalEditCategoryForm #frontend').iCheck('check').iCheck('update');
            }else{
                $('#modalEditCategoryForm #frontend').iCheck('unckeck').iCheck('update');
            }  

            if('auto-desktops' in category){

                $('#modalEditCategoryForm #auto-desktops-enabled').iCheck('check').iCheck('update');
                $("#modalEditCategoryForm #auto-desktops").empty()

                category['auto-desktops'].forEach(function(dom_id){
                    api.ajax('/isard-admin/admin/load/domains/post','POST',{'id':dom_id,'pluck':['id','name']}).done(function(dom) {
                        var newOption = new Option(dom.name, dom.id, true, true);
                        $("#modalEditCategoryForm #auto-desktops").append(newOption).trigger('change');
                    });
                });
                $("#modalEditCategoryForm #auto-desktops-data").show();
            }else{
                $('#modalEditCategoryForm #auto-desktops-enabled').iCheck('unckeck').iCheck('update');
                $("#modalEditCategoryForm #auto-desktops-data").hide();
            } 

            if('ephimeral-action' in category){
                $('#modalEditCategoryForm #ephimeral-enabled').iCheck('check').iCheck('update');
                $("#modalEditCategoryForm #ephimeral-minutes").ionRangeSlider({
                    type: "single",
                    from: category['ephimeral-minutes'],
                    min: 5,
                    max: 120,
                    step:5,
                    grid: true,
                    disable: false
                    }).data("ionRangeSlider").update();
                $('#modalEditCategoryForm #ephimeral-action option[value="'+category['ephimeral-action']+'"]').prop("selected",true); 
                $("#modalEditCategoryForm #ephimeral-data").show();               
            }else{
                $('#modalEditCategoryForm #ephimeral-enabled').iCheck('unckeck').iCheck('update');
                $("#modalEditCategoryForm #ephimeral-data").hide(); 
            }                                       
        });   

        $("#modalEditCategoryForm #ephimeral-enabled").on('ifChecked', function(event){
            $("#modalEditCategoryForm #ephimeral-data").show();
        });
        $("#modalEditCategoryForm #ephimeral-enabled").on('ifUnchecked', function(event){
                    $("#modalEditCategoryForm #ephimeral-data").hide();
        });        

        $("#modalEditCategoryForm #auto-desktops-enabled").on('ifChecked', function(event){
                    $("#modalEditCategoryForm #auto-desktops-data").show();
        });
        $("#modalEditCategoryForm #auto-desktops-enabled").on('ifUnchecked', function(event){
                    $("#modalEditCategoryForm #auto-desktops-data").hide();
        }); 

        $("#modalEditCategory #send").on('click', function(e){
            var form = $('#modalEditCategoryForm');
            form.parsley().validate();
            if (form.parsley().isValid()){
                data=$('#modalEditCategoryForm').serializeObject();
                data['id']=$('#modalEditCategoryForm #id').val();
                data['name']=$('#modalEditCategoryForm #name').val();
                if('frontend' in data){
                    data['frontend']=true
                }
                if(!('ephimeral-enabled' in data)){
                    delete data['ephimeral-minutes'];
                    delete data['ephimeral-action'];
                }
                if(!('auto-desktops-enabled' in data)){
                    delete data['auto-desktops'];
                }
                data['table']='categories';
                socket.emit('role_category_group_add',data)  
            }
        });         
    });
    
    $('.btn-edit-quotas').unbind().on('click', function () {
        var pk=$(this).closest("div").attr("data-pk");

        $("#modalEditQuotaForm")[0].reset();
        $('#modalEditQuotaForm #id').val(pk);
        $('#modalEditQuota').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        setQuotaMax('#modalEditQuotaForm',kind='category',id=pk,disabled=false);        
	});

    $("#modalEditQuota #send").unbind().on('click', function(e){
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
            data['id']=pk
            data['quota']=dataform['quota']
            if('propagate' in formdata){
                data['propagate']=true;
            }            
            data['table']='categories'
            socket.emit('quota_update',data)  
        }
    });

    $('.btn-edit-limits').unbind().on('click', function () {
        var pk=$(this).closest("div").attr("data-pk");

        $("#modalEditLimitsForm")[0].reset();
        $('#modalEditLimitsForm #id').val(pk);
        $('#modalEditLimits').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        setLimitsMax('#modalEditLimitsForm',kind='category',id=pk,disabled=false);         
    });

    $("#modalEditLimits #send").unbind().on('click', function(e){
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
            data['id']=pk
            data['limits']=dataform['limits']
            if('propagate' in formdata){
                data['propagate']=true;
            }
            data['table']='categories'
            socket.emit('quota_update',data)  
        }
    });

	$('.btn-delete').unbind().on('click', function () {
            var pk=$(this).closest("div").attr("data-pk");

            $("#modalDeleteCategoryForm")[0].reset();
            $('#modalDeleteCategoryForm #id').val(pk);
            $('#modalDeleteCategory').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            api.ajax('/isard-admin/admin/category/delete','POST',{'pk':pk}).done(function(domains) {
                $('#table_modal_category_delete tbody').empty()
                $.each(domains, function(key, value) {
                    $('#table_modal_category_delete tbody').append('<tr>\
                                <th>'+value['kind']+'</th>\
                                <th>'+value['user']+'</th>\
                                <th>'+value['name']+'</th>\
                                </tr>');
                });  
           
            });
	    });



        
}
