	function setHardwareOptions(id,default_boot){
        default_boot = typeof default_boot !== 'undefined' ? default_boot : 'hd' ;
			// id is the main div id containing hardware.html
			$(id+" #hardware-interfaces").find('option').remove();
			$(id+" #hardware-graphics").find('option').remove();
            $(id+" #hardware-videos").find('option').remove();
            $(id+" #hardware-boot_order").find('option').remove();
            $(id+" #hypervisors_pools").find('option').remove();
            $(id+" #forced_hyp").find('option').remove();
            
			api.ajax_async('/domains/hardware/allowed','GET','').done(function(hardware) {
                // Needs a hidden input to activate disabled dropdowns...
                //~ if(hardware.nets.length==1){$(id+" #hardware-interfaces").prop('disabled',true);}
				$.each(hardware.nets,function(key, value) 
				{
					$(id+" #hardware-interfaces").append('<option value=' + value.id + '>' + value.name + '</option>');
				});
                
				//~ if(hardware.graphics.length==1){$if(hardware.nets.length==1){$(id+" #hardware-interfaces").prop('disabled',true);}(id+" #hardware-graphics").prop('disabled',true);}
				$.each(hardware.graphics,function(key, value) 
				{
					$(id+" #hardware-graphics").append('<option value=' + value.id + '>' + value.name + '</option>');
				});
                
                //~ if(hardware.videos.length==1){$(id+" #hardware-videos").prop('disabled',true);}
				$.each(hardware.videos,function(key, value) 
				{
					$(id+" #hardware-videos").append('<option value=' + value.id + '>' + value.name + '</option>');
				});
                
                //~ if(hardware.boots.length==1){$(id+" #hardware-boot_order").prop('disabled',true);}
				$.each(hardware.boots,function(key, value) 
				{   
                    //~ if(value.id=='hd'){value.id='disk'}
					$(id+" #hardware-boot_order").append('<option value=' + value.id + '>' + value.name + '</option>');
				});
                $(id+' #hardware-boot_order option[value="'+default_boot+'"]').prop("selected",true);
                
                //~ if(hardware.hypervisors_pools.length==1){$(id+" #hypervisors_pools").prop('disabled',true);}
				$.each(hardware.hypervisors_pools,function(key, value) 
				{   // hypervisors_pools is not inside hardware (take it into account when editing!)
					$(id+" #hypervisors_pools").append('<option value=' + value.id + '>' + value.name + '</option>');
				});

				$.each(hardware.forced_hyps,function(key, value) 
				{   // hypervisors_pools is not inside hardware (take it into account when editing!)
					$(id+" #forced_hyp").append('<option value=' + value.id + '>' + value.hostname+' ('+value.status+')' + '</option>');
				});
                //~ console.log(hardware.user['quota-hardware-memory'])
				$(id+" #hardware-memory").ionRangeSlider({
						  type: "single",
						  min: 500,
						  max: hardware.user['quota-hardware-memory']/1000,
                          step:250,
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider").update();
				$(id+" #hardware-vcpus").ionRangeSlider({
						  type: "single",
						  min: 1,
						  max: hardware.user['quota-hardware-vcpus'],
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider").update();
                if($(id+" #disk_size").length != 0) {
                    if(hardware.user['quota-domains-desktops_disk_max']/1000000>200){
                        var dsize=120;}else{ var dsize=(hardware.user['quota-domains-desktops_disk_max']/1000000).toFixed(1);}
                    $(id+" #disk_size").ionRangeSlider({
                              type: "single",
                              min: 1,
                              max: dsize,
                              grid: true,
                              disable: false
                              }).data("ionRangeSlider").update();
                }
			}); 
	}
    
	function setHardwareDomainDefaults(div_id,domain_id){
			// id is the domain id
            //~ console.log('setHardwareDomainDefaults')
            $(div_id+' #hardware-interfaces option:selected').prop("selected", false);
            $(div_id+' #hardware-graphics option:selected').prop("selected", false);
            $(div_id+' #hardware-videos option:selected').prop("selected", false);
            $(div_id+' #hardware-boot_order option:selected').prop("selected", false);
            $(div_id+' #hypervisors_pools option:selected').prop("selected", false);
            
			api.ajax('/domains/hardware','POST',{'pk':domain_id}).done(function(domain) {
				$(div_id+' #hardware-interfaces option[value="'+domain.hardware.interfaces[0].id+'"]').prop("selected",true);
				$(div_id+' #hardware-graphics option[value="'+domain.hardware.graphics.type+'"]').prop("selected",true);
                $(div_id+' #hardware-videos option[value="'+domain.hardware.video.type+'"]').prop("selected",true);
                $(div_id+' #hardware-diskbus option[value="'+domain.hardware.disks[0].bus+'"]').prop("selected",true);
                
                // Need to talk with engine and change this
                if(domain.hardware.boot_order[0]=='hd'){domain.hardware.boot_order[0]='disk'}
                if(domain.hardware.boot_order[0]=='cdrom'){domain.hardware.boot_order[0]='iso'}
                if(domain.hardware.boot_order[0]=='network'){domain.hardware.boot_order[0]='pxe'}
                $(div_id+' #hardware-boot_order option[value="'+domain.hardware.boot_order[0]+'"]').prop("selected",true);
                
                $(div_id+' #hypervisors_pools option[value="'+domain['hypervisors_pools'][0]+'"]').prop("selected",true);
                if(domain['forced_hyp']){
                    $(div_id+' #forced_hyp option[value="'+domain['forced_hyp']+'"]').prop("selected",true);
                }
				$(div_id+" #hardware-memory").data("ionRangeSlider").update({
						  from: domain.hardware.memory/1000
                });
				$(div_id+" #hardware-vcpus").data("ionRangeSlider").update({
						  from: domain.hardware.vcpus
                });
					  
			}); 
	}

	//~ function setHardwareUserDefaults(div_id,user){
			//~ // id is the domain id
            //~ $(div_id+' #hardware-interfaces option:selected').prop("selected", false);
            //~ $(div_id+' #hardware-graphics option:selected').prop("selected", false);
            //~ $(div_id+' #hardware-videos option:selected').prop("selected", false);
            //~ $(div_id+' #hardware-boot_order option:selected').prop("selected", false);
            //~ $(div_id+' #hypervisors_pools option:selected').prop("selected", false);
            
			//~ api.ajax('/userhardwarequota','POST',{'pk':domain_id}).done(function(domain) {
				//~ $(div_id+' #hardware-interfaces option[value="'+domain['hardware-interfaces'][0].id+'"]').prop("selected",true);
				//~ $(div_id+' #hardware-graphics option[value="'+domain['hardware-graphics-type']+'"]').prop("selected",true);
                //~ $(div_id+' #hardware-videos option[value="'+domain['hardware-video-type']+'"]').prop("selected",true);
                
                //~ // Need to talk with engine and change this
                //~ if(domain['hardware-boot_order'][0]=='hd'){domain['hardware-boot_order'][0]='disk'}
                //~ if(domain['hardware-boot_order'][0]=='cdrom'){domain['hardware-boot_order'][0]='iso'}
                //~ if(domain['hardware-boot_order'][0]=='network'){domain['hardware-boot_order'][0]='pxe'}
                //~ $(div_id+' #hardware-boot_order option[value="'+domain['hardware-boot_order'][0]+'"]').prop("selected",true);
                
                //~ $(div_id+' #hypervisors_pools option[value="'+domain['hypervisors_pools'][0]+'"]').prop("selected",true);
                //~ if(domain['forced_hyp']){
                    //~ $(div_id+' #forced_hyp option[value="'+domain['forced_hyp']+'"]').prop("selected",true);
                //~ }
				//~ $(div_id+" #hardware-memory").data("ionRangeSlider").update({
						  //~ from: domain['hardware-memory']/1000
                //~ });
				//~ $(div_id+" #hardware-vcpus").data("ionRangeSlider").update({
						  //~ from: domain['hardware-vcpus']
                //~ });
					  
			//~ }); 
	//~ }
    
	function setHardwareDomainDefaults_viewer(div_id,data){
	    if(data["hardware"]  != undefined){
		$(div_id+" #vcpu").html(data.hardware.vcpus+' CPU(s)');
		$(div_id+" #ram").html(data.hardware.memory+data.hardware.memory_unit);
		// List could not be ordered! In theory all the disks have same virtual-size
                //~ $(div_id+" #disks").html(domain['disks_info'][0]['virtual-size']);
	    $(div_id+" #net").html(data.hardware.interfaces[0].id);
	    $(div_id+" #graphics").html(data.hardware.graphics.type);
                $(div_id+" #video").html(data.hardware.video.type);
                $(div_id+" #boot").html(data.hardware['boot_order']);
                $(div_id+" #hypervisor_pool").html(data['hypervisors_pools'][0]);
                if(data['forced_hyp']){
                    $(div_id+" #forced_hyp").html(data['forced_hyp']);
                    $(div_id+" #forced_hyp").closest("tr").show();
                }else{
                    $(div_id+" #forced_hyp").closest("tr").hide(); //.closest("tr").remove();
                }
            }
			//~ }); 
	}



