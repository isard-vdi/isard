	function setDomainDerivates(id){
			api.ajax('/domain_derivates','POST',{'pk':id}).done(function(derivates) {
                var wasted=0
                $.each(derivates,function(index,val){
                    $("#table-derivates-"+id).append('<tr><td>'+val['name']+'</td><td>'+val['kind']+'</td><td>'+val['user']+'</td></tr>');
                });  
            });
            
    }
    
