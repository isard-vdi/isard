	function setQuotaOptions(parentid){
        api.ajax('/hardware','GET','').done(function(hardware) {
            user=hardware.user
            parentid=parentid+' ';
				$(parentid+"#quota-domains-desktops").ionRangeSlider({
						  type: "single",
						  min: 1,
						  max: user['quota-domains-desktops'],
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider");
				$(parentid+"#quota-domains-running").ionRangeSlider({
						  type: "single",
						  min: 1,
						  max: user['quota-domains-running'],
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider");	
				$(parentid+"#quota-domains-templates").ionRangeSlider({
						  type: "single",
						  min: 1,
						  max: user['quota-domains-templates'],
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

	function setQuotatABLEDefaults(div_id,table){
			// id is the domain id
            $(div_id+' #quota-domains-desktops option:selected').prop("selected", false);
            $(div_id+' #quota-domains-running option:selected').prop("selected", false);
            $(div_id+' #quota-domains-templates option:selected').prop("selected", false);
            $(div_id+' #quota-domains-isos option:selected').prop("selected", false);
            
			api.ajax('/admin/table/'+table+'/get','GET',{}).done(function(domain) {
				$(div_id+' #quota-domains-desktops option[value="'+domain['quota-domains-desktops'][0].id+'"]').prop("selected",true);
				$(div_id+' #quota-domains-running option[value="'+domain['quota-domains-running']+'"]').prop("selected",true);
                $(div_id+' #quota-domains-templates option[value="'+domain['quota-domains-templates']+'"]').prop("selected",true);
                $(div_id+' #quota-domains-isos_order option[value="'+domain['quota-domains-isos'][0]+'"]').prop("selected",true);
				$(div_id+" #quota-hardware-memory").data("ionRangeSlider").update({
						  from: domain['quota-hardware-memory']/1000
                });
				$(div_id+" #quota-hardware-vcpus").data("ionRangeSlider").update({
						  from: domain['quota-hardware-vcpus']
                });
					  
			}); 
	}

	//~ function setHardwareDomainDefaults_viewer(div_id,domain_id){
			//~ api.ajax('/domain','POST',{'pk':domain_id,'hs':true}).done(function(domain) {
				//~ $(div_id+" #vcpu").html(domain['hardware-vcpus']+' CPU(s)');
				//~ $(div_id+" #ram").html(domain['hardware-memory']);
                //~ // List could not be ordered! In theory all the disks have same virtual-size
                //~ $(div_id+" #disks").html(domain['disks_info'][0]['virtual-size']);
				//~ $(div_id+" #net").html(domain['hardware-interfaces'][0].id);
				//~ $(div_id+" #graphics").html(domain['hardware-graphics-type']);
                //~ $(div_id+" #video").html(domain['hardware-video-type']);
                //~ $(div_id+" #boot").html(domain['hardware-boot_order']);
                //~ $(div_id+" #hypervisor_pool").html(domain['hypervisors_pools'][0]);
			//~ }); 
	//~ }



