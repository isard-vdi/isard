	function setReservablesOptions(id){
			// id is the main div id containing hardware.html
			$(id+" #reservables-vgpus").find('option').remove();
			
			api.ajax_async('/api/v3/domains/allowed/reservables','GET','').done(function(reservables) {
				if(reservables.vgpus.length == 1){
					$(id+" #reservables-vgpus").attr("disabled",true);
				}else{
					$(id+" #reservables-vgpus").attr("disabled",false);
				}
				$.each(reservables.vgpus,function(key, value) 
				{
					$(id+" #reservables-vgpus").append('<option value=' + value.id + '>' + value.name + ' - ' + value.description + '</option>');
				});
			}); 
	}
    
	function setReservablesDomainDefaults(div_id,domain_id){
			// id is the domain id
			$(div_id+' #reservables-vgpus option:selected').prop("selected", false);
			api.ajax('/api/v3/domains/allowed/reservables/defaults/'+domain_id,'GET','').done(function(domain) {
				if(domain.hasOwnProperty("reservables") && "vgpus" in domain.reservables && domain.reservables.vgpus && domain.reservables.vgpus[0]){
					if ($(div_id+' #reservables-vgpus option[value="'+domain.reservables.vgpus[0]+'"]').length == 0) {
						 $(div_id+" #reservables-vgpus").append('<option disabled value=' + domain.reservables.vgpus[0] + '>' + domain.reservables.vgpus[0] + '</option>')
					}
					$(div_id+' #reservables-vgpus option[value="'+domain.reservables.vgpus[0]+'"]').prop("selected",true);
				}else{
					$(div_id+' #reservables-vgpus option[value="None"]').prop("selected",true);  
				}
			}); 
	}
