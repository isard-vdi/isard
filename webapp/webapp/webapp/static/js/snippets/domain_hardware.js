	function setHardwareOptions(id,default_boot){
        default_boot = typeof default_boot !== 'undefined' ? default_boot : 'hd' ;
			// id is the main div id containing hardware.html
			$(id+" #hardware-memory").find('option').remove();
			$(id+" #hardware-vcpus").find('option').remove();
			$(id+" #hardware-interfaces").find('option').remove();
			$(id+" #hardware-graphics").find('option').remove();
            $(id+" #hardware-videos").find('option').remove();
			$(id+" #hardware-boot_order").find('option').remove();
			$(id+" #hardware-qos_id").find('option').remove();
			
			api.ajax_async('/isard-admin/domains/hardware/allowed','GET','').done(function(hardware) {
				if(hardware.nets.length == 1){
					$(id+" #hardware-interfaces").attr("disabled",true);
				}else{
					$(id+" #hardware-interfaces").attr("disabled",false);
				}
				$.each(hardware.nets,function(key, value) 
				{
					$(id+" #hardware-interfaces").append('<option value=' + value.id + '>' + value.name + '</option>');
				});

				if(hardware.graphics.length == 1){
					$(id+" #hardware-graphics").attr("disabled",true);
				}else{
					$(id+" #hardware-graphics").attr("disabled",false);
				}
				$.each(hardware.graphics,function(key, value) 
				{
					$(id+" #hardware-graphics").append('<option value=' + value.id + '>' + value.name + '</option>');
				});

				if(hardware.videos.length == 1){
					$(id+" #hardware-videos").attr("disabled",true);
				}else{
					$(id+" #hardware-videos").attr("disabled",false);
				}
				$.each(hardware.videos,function(key, value) 
				{
					$(id+" #hardware-videos").append('<option value=' + value.id + '>' + value.name + '</option>');
				});

				if(hardware.boots.length == 1){
					$(id+" #hardware-boot_order").attr("disabled",true);
				}else{
					$(id+" #hardware-boot_order").attr("disabled",false);
				}
				$.each(hardware.boots,function(key, value) 
				{   
					$(id+" #hardware-boot_order").append('<option value=' + value.id + '>' + value.name + '</option>');
				});
                $(id+' #hardware-boot_order option[value="'+default_boot+'"]').prop("selected",true);

				if(hardware.qos_id.length <= 1 || !('qos_id' in hardware)){
					$(id+" #hardware-qos_id").attr("disabled",true);
				}else{
					$(id+" #hardware-qos_id").attr("disabled",false);
				}
				if(hardware.qos_id.length == 0){
					$(id+" #hardware-qos_id").append('<option value="unlimited">Unlimited</option>');
				}else{
					$.each(hardware.qos_id,function(key, value) 
					{
						$(id+" #hardware-qos_id").append('<option value=' + value.id + '>' + value.name + '</option>');
					});
				}

				if(hardware.quota == false){
					hardware.quota={'memory':128, 'vcpus':128, 'desktops_disk_size':500}
				}
	
				for (var i = 0.5; i <= hardware.quota.memory; i += 0.5) {
					$(id+" #hardware-memory").append('<option value='+i+'>' + i +'</option>');
				}

				for (var i = 1; i <= hardware.quota.vcpus; i += 1) {
					$(id+" #hardware-vcpus").append('<option value='+i+'>' + i +' vCPU</option>');
				}	

				if($(id+" #disk_size").length != 0) {
					$(id+" #disk_size").find('option').remove();
					if(hardware.quota.desktops_disk_size <= 10){
						for (var i = 1; i <= hardware.quota.desktops_disk_size; i += 1) {
							$(id+" #disk_size").append('<option value='+i+'>' + i +' GB</option>');
						}
					}else{
						$(id+" #disk_size").append('<option value=1>1 GB</option>');
						$(id+" #disk_size").append('<option value=5>5 GB</option>');
						for (var i = 10; i <= hardware.quota.desktops_disk_size; i += 5) {
							$(id+" #disk_size").append('<option value='+i+'>' + i +' GB</option>');
						}
					}	
				}
				
			}); 
	}
    
	function setHardwareDomainDefaults(div_id,domain_id){
			// id is the domain id
            $(div_id+' #hardware-interfaces option:selected').prop("selected", false);
            $(div_id+' #hardware-graphics option:selected').prop("selected", false);
            $(div_id+' #hardware-videos option:selected').prop("selected", false);
            $(div_id+' #hardware-boot_order option:selected').prop("selected", false);
			api.ajax('/isard-admin/domains/hardware','POST',{'pk':domain_id}).done(function(domain) {
				$.each(domain.hardware.interfaces, function(k,value){
					$(div_id+' #hardware-interfaces option[value="'+value+'"]').prop("selected",true);
				})
				$(div_id+' #hardware-graphics option[value="'+domain.hardware.graphics[0].type+'"]').prop("selected",true);
                $(div_id+' #hardware-videos option[value="'+domain.hardware.videos[0]+'"]').prop("selected",true);
                $(div_id+' #hardware-diskbus option[value="'+domain.hardware.disks[0].bus+'"]').prop("selected",true);
                
                // Need to talk with engine and change this
                if(domain.hardware.boot_order[0]=='hd'){domain.hardware.boot_order[0]='disk'}
                if(domain.hardware.boot_order[0]=='cdrom'){domain.hardware.boot_order[0]='iso'}
                if(domain.hardware.boot_order[0]=='network'){domain.hardware.boot_order[0]='pxe'}
                $(div_id+' #hardware-boot_order option[value="'+domain.hardware.boot_order[0]+'"]').prop("selected",true);

				if(domain.hardware.memory > $(div_id+' #hardware-memory option:last-child').val()){
					$(div_id+' #hardware-memory option:last-child').prop("selected",true);
				}else{
					if($(div_id+' #hardware-memory option[value="'+domain.hardware.memory+'"]').length > 0){
						$(div_id+' #hardware-memory option[value="'+domain.hardware.memory+'"]').prop("selected",true);
					}else{
						$(div_id+' #hardware-memory option:first').prop("selected",true);
					}
				}

				if(domain.hardware.vcpus > $(div_id+' #hardware-vcpus option:last-child').val()){
					$(div_id+' #hardware-vcpus option:last-child').prop("selected",true);
				}else{
					if($(div_id+' #hardware-vcpus option[value="'+domain.hardware.vcpus+'"]').length > 0){
						$(div_id+' #hardware-vcpus option[value="'+domain.hardware.vcpus+'"]').prop("selected",true);
					}else{
						$(div_id+' #hardware-vcpus option:first').prop("selected",true);
					}
				}
				
				if('qos_id' in domain.hardware.disks[0]){
					if(domain.hardware.disks[0]['qos_id']==false){
						qos_id='unlimited'
					}else{
						qos_id=domain.hardware.disks[0]['qos_id']
					}
				}else{
					qos_id='unlimited'
				}

				$(div_id+' #hardware-qos_id option[value="'+qos_id+'"]').prop("selected",true);	  
			}); 
	}

	function setHardwareDomainDefaults_viewer(div_id,data){
		data['hardware']=data['create_dict']['hardware']
		$(div_id+" #vcpu").html(data.hardware.vcpus+' CPU(s)');
		$(div_id+" #ram").html((data.hardware.memory/1048576).toFixed(2)+'GB');
	    	$(div_id+" #net").html(data.hardware.interfaces);
	    	$(div_id+" #graphics").html(data.hardware.graphics);
		$(div_id+" #video").html(data.hardware.videos);
		$(div_id+" #boot").html(data.hardware['boot_order']);
		$(div_id+" #hypervisor_pool").html(data['hypervisors_pools']);
		if(data['forced_hyp']){
			$(div_id+" #forced_hyp").html(data['forced_hyp']);
			$(div_id+" #forced_hyp").closest("tr").show();
		}else{
			$(div_id+" #forced_hyp").closest("tr").hide(); //.closest("tr").remove();
		}
	}



