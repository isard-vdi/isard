

	function replaceMedia_arrays(parent_id,data){
        data['create_dict']={'hardware':{'isos':    parseMedia(parent_id,'m-isos'),
                                        'floppies': parseMedia(parent_id,'m-floppies')}}
        delete data['m-isos'];
        delete data['m-floppies'];
        return data
    }
        
    function parseMedia(parent_id,id){
        d=$(parent_id+" #"+id).select2("val")
        if(d==null){
                return [];
        }
        nd=[]
        d.forEach(function(data)
        { 
            nd.push({'id':data})
        });      
        return nd
    }
	


 	
	function setMedia_add(parentid){
		ids=['m-isos','m-floppies']
		 $.each(ids,function(idx,id) {
			 $(parentid+" #"+id).select2({
				minimumInputLength: 2,
				multiple: true,
				ajax: {
					type: "POST",
					url: '/media/select2/post',
					dataType: 'json',
					contentType: "application/json",
					delay: 250,
					data: function (params) {
						return  JSON.stringify({
							term: params.term,
							pluck: ['id','name'],
                            kind: id.replace('m-','')
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
    

	function setDomainMediaDefaults(div_id,domain_id){
			// id is the domain id
            api.ajax('/domain/media','POST',{'pk':domain_id}).done(function(kinds) {
                $.each(kinds,function(key, value) 
                {   
                        $(div_id+"  #m-"+key).empty().trigger('change')
                        if(value){
                            value.forEach(function(data)
                            {                                  
                                var newOption = new Option(data.name, data.id, true, true);
                                 $(div_id+"  #m-"+key).append(newOption).trigger('change');
                            });
                        }
                });
            });

	}
    
    
 
