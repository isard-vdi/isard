	function setQuotaOptions(parentid){
        api.ajax('/hardware','GET','').done(function(hardware) {
            user=hardware.user
            parentid=parentid+' ';
				$(parentid+"#quota-domains-desktops").ionRangeSlider({
						  type: "single",
						  min: 1,
						  max: user['quota-domains-isos'],
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider");
				$(parentid+"#quota-domains-running").ionRangeSlider({
						  type: "single",
						  min: 1,
						  max: user['quota-domains-isos'],
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider");	
				$(parentid+"#quota-domains-templates").ionRangeSlider({
						  type: "single",
						  min: 1,
						  max: user['quota-domains-isos'],
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider");		
				$(parentid+"#quota-domains-isos").ionRangeSlider({
						  type: "single",
						  min: 1,
						  max: user['quota-domains-isos'],
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider");	
				$(parentid+"#quota-hardware-memory").ionRangeSlider({
						  type: "single",
						  min: 1000,
						  max: user['quota-hardware-memory']/1000,
                          step: 250,
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider");
				$(parentid+"#quota-hardware-vcpus").ionRangeSlider({
						  type: "single",
						  min: 1,
						  max: user['quota-hardware-vcpus'],
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider");	
        });
    }; 

    function quota2dict(data){
         data['quota']={'hardware':{},'domains':{}}
         hwids=['vcpus','memory']
		 $.each(hwids,function(idx,id){
            delete data['quota-hardware-'+id];
            data['quota']['hardware'][id]=parseInt($('#quota-hardware-'+id).val())  || 0
         });
         
         dmids=['desktops','running','templates','isos']
		 $.each(dmids,function(idx,id){
            delete data['quota-domains-'+id];
            data['quota']['domains'][id]=parseInt($('#quota-domains-'+id).val())  || 0
         });         
        return data
    }

	function setHardwareDomainDefaults(div_id,domain_id){
			// id is the domain id
            $(div_id+' #hardware-interfaces option:selected').prop("selected", false);
            $(div_id+' #hardware-graphics option:selected').prop("selected", false);
            $(div_id+' #hardware-videos option:selected').prop("selected", false);
            $(div_id+' #hardware-boot_order option:selected').prop("selected", false);
            $(div_id+' #hypervisors_pools option:selected').prop("selected", false);
            
			api.ajax('/domain','POST',{'pk':domain_id}).done(function(domain) {
				$(div_id+' #hardware-interfaces option[value="'+domain['hardware-interfaces'][0].id+'"]').prop("selected",true);
				$(div_id+' #hardware-graphics option[value="'+domain['hardware-graphics-type']+'"]').prop("selected",true);
                $(div_id+' #hardware-videos option[value="'+domain['hardware-video-type']+'"]').prop("selected",true);
                $(div_id+' #hardware-boot_order option[value="'+domain['hardware-boot_order'][0]+'"]').prop("selected",true);
                $(div_id+' #hypervisors_pools option[value="'+domain['hypervisors_pools'][0]+'"]').prop("selected",true);
				$(div_id+" #hardware-memory").data("ionRangeSlider").update({
						  from: domain['hardware-memory']/1000
                });
				$(div_id+" #hardware-vcpus").data("ionRangeSlider").update({
						  from: domain['hardware-vcpus']
                });
					  
			}); 
	}

	function setHardwareDomainDefaults_viewer(div_id,domain_id){
			api.ajax('/domain','POST',{'pk':domain_id,'hs':true}).done(function(domain) {
				$(div_id+" #vcpu").html(domain['hardware-vcpus']+' CPU(s)');
				$(div_id+" #ram").html(domain['hardware-memory']);
                // List could not be ordered! In theory all the disks have same virtual-size
                $(div_id+" #disks").html(domain['disks_info'][0]['virtual-size']);
				$(div_id+" #net").html(domain['hardware-interfaces'][0].id);
				$(div_id+" #graphics").html(domain['hardware-graphics-type']);
                $(div_id+" #video").html(domain['hardware-video-type']);
                $(div_id+" #boot").html(domain['hardware-boot_order']);
                $(div_id+" #hypervisor_pool").html(domain['hypervisors_pools'][0]);
			}); 
	}

    function setHardwareGraph() {
        // Not implemented
    }


