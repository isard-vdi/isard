
	function setAlloweds_viewer(div_id,id){
			api.ajax('/domain/alloweds','POST',{'pk':id}).done(function(alloweds) {
                var all=false;
                $.each(alloweds,function(key, value) 
                {
                    if(typeof value !== 'undefined' && value.length == 0){all=true;}
                });
                if(all){
                    $(div_id+" #table-alloweds-"+id).append('<tr><td>Everyone</td><td>Has access</td></tr>');
                }else{
                    $.each(alloweds,function(key, value) 
                    {   
                        if(value){
                                $(div_id+" #table-alloweds-"+id).append('<tr><td>'+key+'</td><td>'+value+'</td></tr>');
                        }

                    });
                }
			}); 
	}

	function replaceAlloweds_arrays(data){
		ids=['a-roles','a-categories','a-groups','a-users']
		data['allowed']={}
		 $.each(ids,function(idx,id) 
         { 
			 delete data[id];
			 val = $('#'+id).val()  || false
			 if(!(val) && id+'-cb' in data){val=[];}
			 delete data[id+'-cb'];
			 data['allowed'][id.replace('a-','')] = val; 
		 });
		 
		 return data
	}


 	
	function setAlloweds_add(parentid){
		ids=['a-roles','a-categories','a-groups','a-users']
		 $.each(ids,function(idx,id) 
         {   $(parentid+' #'+id+'-cb').iCheck('uncheck');
			 $(parentid+' #'+id+'-cb').on('ifChecked', function(event){
				  $(parentid+" #"+id).attr('disabled',false);
			 });
			 $(parentid+' #'+id+'-cb').on('ifUnchecked', function(event){
				  $(parentid+" #"+id).attr('disabled',true);
			 });
			 $(parentid+" #"+id).attr('disabled',true);
			 //~ console.log(id)
			 $(parentid+" #"+id).select2({
				minimumInputLength: 2,
				multiple: true,
				ajax: {
					type: "POST",
					url: '/admin/table/'+id.replace('a-','')+'/post',
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
		});
	
	}
    
    
    
    function modalAllowedsFormShow(table,data){

                    $('#modalAlloweds #alloweds_name').html(data.name)
                    $('#modalAllowedsForm #id').val(data.id);
                    $('#modalAlloweds #alloweds_panel').show()
                    $("#modalAllowedsForm")[0].reset();
                    $('#modalAlloweds').modal({
                        backdrop: 'static',
                        keyboard: false
                    }).modal('show');
                    //~ $('#modalAllowedsForm').parsley();
                    setAlloweds_add('#modalAlloweds #alloweds-add'); 
                    
                    //~ ids=['a-roles','a-categories','a-groups','a-users']
                     //~ $.each(ids,function(idx,id) 
                     //~ {   $(parentid+' #'+id+'-cb').iCheck('uncheck');
                         //~ $(parentid+' #'+id+'-cb').on('ifChecked', function(event){
                              //~ $(parentid+" #"+id).attr('disabled',false);
                         //~ });
             
                    api.ajax('/domain/alloweds/select2','POST',{'pk':data.id,'allowed':data.allowed}).done(function(alloweds) {
                        
                    
                        $.each(alloweds,function(key, value) 
                        {   
                            //~ console.log(key)
                            //~ console.log(value)
                            console.log('a-'+key)
                            if(value){
                                console.log(value)
                                    $("#modalAllowedsForm #alloweds-add a-"+key).select2({data: value});
                            }

                        });
                    });

                           
    }


	
