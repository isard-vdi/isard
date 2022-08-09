function unlimited_show_hide(parentid, selector, editable, unlimited){
	if(editable) {
		$(parentid).find(".unlimited").show()
		$(parentid).find("label[for=unlimited]").show()
		$(parentid).find(".unlimited .checkbox").show()
		$(parentid).find(".quota_form").show()
		if (unlimited) {
			quotaDisable(selector)
		} else {
			quotaEnable(selector)
		}
	} else {
		quotaDisable(selector)
		if (unlimited) {
			$(parentid).find(".unlimited").show()
			$(parentid).find("label[for=unlimited]").show()
		} else {
			$(parentid).find(".quota_form").show()
		}
	}
}

	function setQuotaMax(parentid,kind,id,disabled){
		disabled = typeof disabled !== 'undefined' ? disabled : false;
		id = typeof id !== 'undefined' ? id : false; //Missing id will get current user/category/group
		if(id == false){
			url='/api/v3/quota/'+kind;
		}else{
			url='/api/v3/quota/'+kind+'/'+id;
		}

        api.ajax(url,'GET','').done(function(usrquota) {
            parentid=parentid+' ';
			$(parentid+"#quota-desktops").removeAttr("max");
			$(parentid+"#quota-desktops_disk_size").removeAttr("max");
			$(parentid+"#quota-running").removeAttr("max");
			$(parentid+"#quota-templates").removeAttr("max");
			$(parentid+"#quota-templates_disk_size").removeAttr("max");		
			$(parentid+"#quota-isos").removeAttr("max");
			$(parentid+"#quota-isos_disk_size").removeAttr("max");	
			$(parentid+"#quota-memory").removeAttr("max");
			$(parentid+"#quota-vcpus").removeAttr("max");

			
			
			// ONLY FOR KIND=USER
			// if limits are defined for user set as max value
			// Limits for user are the limits from his group or, if false, from his category.
			// Admins don't have limits at all
			if(usrquota.limits != false){
				$(parentid+"#quota-desktops").attr("max", usrquota.limits.desktops);
				$(parentid+"#quota-desktops_disk_size").attr("max", usrquota.limits.desktops_disk_size);
				$(parentid+"#quota-running").attr("max", usrquota.limits.running);	
				$(parentid+"#quota-templates").attr("max", usrquota.limits.templates);	
				$(parentid+"#quota-templates_disk_size").attr("max", usrquota.limits.templates_disk_size);	
				$(parentid+"#quota-isos").attr("max", usrquota.limits.isos);
				$(parentid+"#quota-isos_disk_size").attr("max", usrquota.limits.isos_disk_size);	
				$(parentid+"#quota-memory").attr("max", usrquota.limits.memory);
				$(parentid+"#quota-vcpus").attr("max", usrquota.limits.vcpus);	

				$(parentid+"#quota-desktops").attr("title", "Limit: "+usrquota.limits.desktops);
				$(parentid+"#quota-desktops_disk_size").attr("title", "Limit: "+usrquota.limits.desktops_disk_size);
				$(parentid+"#quota-running").attr("title", "Limit: "+usrquota.limits.running);	
				$(parentid+"#quota-templates").attr("title", "Limit: "+usrquota.limits.templates);	
				$(parentid+"#quota-templates_disk_size").attr("title", "Limit: "+usrquota.limits.templates_disk_size);	
				$(parentid+"#quota-isos").attr("title", "Limit: "+usrquota.limits.isos);
				$(parentid+"#quota-isos_disk_size").attr("title", "Limit: "+usrquota.limits.isos_disk_size);	
				$(parentid+"#quota-memory").attr("title", "Limit: "+usrquota.limits.memory);
				$(parentid+"#quota-vcpus").attr("title", "Limit: "+usrquota.limits.vcpus);				
			}

			if(usrquota.quota != false){
				$(parentid+"#unlimited").removeAttr('checked').iCheck('update');
				enable=true
				$(parentid+"#quota-desktops").val(usrquota.quota.desktops);
				$(parentid+"#quota-desktops_disk_size").val(usrquota.quota.desktops_disk_size);
				$(parentid+"#quota-running").val(usrquota.quota.running);	
				$(parentid+"#quota-templates").val(usrquota.quota.templates);
				$(parentid+"#quota-templates_disk_size").val(usrquota.quota.templates_disk_size);		
				$(parentid+"#quota-isos").val(usrquota.quota.isos);	
				$(parentid+"#quota-isos_disk_size").val(usrquota.quota.isos_disk_size);
				$(parentid+"#quota-memory").val(usrquota.quota.memory);
				$(parentid+"#quota-vcpus").val(usrquota.quota.vcpus);	
			}else{
				$(parentid+"#unlimited").iCheck('check');  
				enable=false
			}

			unlimited_show_hide(parentid, parentid + ' #quota-', !disabled, !enable)

			$(parentid+"#unlimited").unbind('ifChecked').on('ifChecked', function(event){
				quotaDisable('#'+$(event.target).closest('form').attr('id')+' #quota-')
			  }); 	
			$(parentid+"#unlimited").unbind('ifUnchecked').on('ifUnchecked', function(event){
				quotaEnable('#'+$(event.target).closest('form').attr('id')+' #quota-')
			}); 			
        });
    }; 

	function setLimitsMax(parentid,kind,id,disabled){

		disabled = typeof disabled !== 'undefined' ? disabled : false;
		id = typeof id !== 'undefined' ? id : false;
		if(id == false){
			url='/api/v3/quota/'+kind;
		}else{
			url='/api/v3/quota/'+kind+'/'+id;
		}
        api.ajax(url,'GET','').done(function(usrquota) {
			parentid=parentid+' ';

			if(usrquota.limits != false){
				$(parentid+"#unlimited").removeAttr('checked').iCheck('update');
				enable=true
				$(parentid+"#limits-users").val(usrquota.limits.users);	
				$(parentid+"#limits-desktops").val(usrquota.limits.desktops);
				$(parentid+"#limits-desktops_disk_size").val(usrquota.limits.desktops_disk_size);				
				$(parentid+"#limits-running").val(usrquota.limits.running);	
				$(parentid+"#limits-templates").val(usrquota.limits.templates);		
				$(parentid+"#limits-templates_disk_size").val(usrquota.limits.templates_disk_size);	
				$(parentid+"#limits-isos").val(usrquota.limits.isos);	
				$(parentid+"#limits-isos_disk_size").val(usrquota.limits.isos_disk_size);					
				$(parentid+"#limits-memory").val(usrquota.limits.memory);
				$(parentid+"#limits-vcpus").val( usrquota.limits.vcpus);	
			}else{
				$(parentid+"#unlimited").iCheck('check');  
				enable=false
				      
			}

			unlimited_show_hide(parentid, parentid + ' #limits-', !disabled, !enable)

			$(parentid+"#unlimited").unbind('ifChecked').on('ifChecked', function(event){
				quotaDisable('#'+$(event.target).closest('form').attr('id')+' #limits-')
			  }); 	
			$(parentid+"#unlimited").unbind('ifUnchecked').on('ifUnchecked', function(event){
				quotaEnable('#'+$(event.target).closest('form').attr('id')+' #limits-')
			}); 

        });
	}; 

	function quotaEnable(parentid){
		$(parentid+"users").removeAttr("disabled");
		$(parentid+"desktops").removeAttr("disabled");
		$(parentid+"desktops_disk_size").removeAttr("disabled");				
		$(parentid+"running").removeAttr("disabled");
		$(parentid+"templates").removeAttr("disabled");
		$(parentid+"templates_disk_size").removeAttr("disabled");		
		$(parentid+"isos").removeAttr("disabled");	
		$(parentid+"isos_disk_size").removeAttr("disabled");
		$(parentid+"memory").removeAttr("disabled");
		$(parentid+"vcpus").removeAttr("disabled");
	}

	function quotaDisable(parentid){
		$(parentid+"users").attr("disabled", true);
		$(parentid+"desktops").attr("disabled", true);
		$(parentid+"desktops_disk_size").attr("disabled", true);				
		$(parentid+"running").attr("disabled", true);
		$(parentid+"templates").attr("disabled", true);
		$(parentid+"templates_disk_size").attr("disabled", true);	
		$(parentid+"isos").attr("disabled", true);
		$(parentid+"isos_disk_size").attr("disabled", true);	
		$(parentid+"memory").attr("disabled", true);
		$(parentid+"vcpus").attr("disabled", true);
	}

    function quota2dict(data){
		 d={'quota':{},'limits':{}}
         $.each(data,function(key,value){
             if(key.startsWith('quota')){
                 d['quota'][key.split('-')[1]] = parseInt(value)  || 0
             }
             if(key.startsWith('limits')){
                 d['limits'][key.split('-')[1]] = parseInt(value)  || 0
             }                 
         })
        return d;
    }

    function userQuota2dict(data){
		data['quota']={}
		$.each(data,function(key,value){
			if(key.startsWith('quota-')){
				if(!('unlimited' in data)){
					data['quota'][key.split('-')[1]] = parseInt(value)  || 0
				}
				delete data[key];
			}           
		})
		if('unlimited' in data){
			data['quota']=false
		}
		return data;
   }

	//~ Used in users.js
	function setQuotaTableDefaults(div_id,table,id){
			api.ajax('/api/v3/admin/table/'+table,'POST',{'id':id}).done(function(domain) {
				$(div_id+" #quota-desktops").data("ionRangeSlider").update({
						  from: domain['quota-desktops']
                });
				$(div_id+" #quota-running").data("ionRangeSlider").update({
						  from: domain['quota-running']
                });
                $(div_id+" #quota-templates").data("ionRangeSlider").update({
						  from: domain['quota-templates']
                });
				$(div_id+" #quota-isos").data("ionRangeSlider").update({
						  from: domain['quota-isos']
                });                

				$(div_id+" #quota-memory").data("ionRangeSlider").update({
						  from: domain['quota-memory']/1000
                });
				$(div_id+" #quota-vcpus").data("ionRangeSlider").update({
						  from: domain['quota-vcpus']
                });
			}); 
        
	}

