// Not implemented at all

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
