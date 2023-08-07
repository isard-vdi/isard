function setHardwareOptions(id,default_boot,domain_id){
    default_boot = typeof default_boot !== 'undefined' ? default_boot : 'hd' ;
        // id is the main div id containing hardware.html
        $(id+" #hardware-virtualization_nested").find('option').remove();
        $(id+" #hardware-memory").find('option').remove();
        $(id+" #hardware-vcpus").find('option').remove();
        $(id+" #hardware-interfaces").find('option').remove();
        $(id+" #hardware-videos").find('option').remove();
        $(id+" #hardware-boot_order").find('option').remove();
        $(id+" #hardware-qos_id").find('option').remove();
        $(id+" #hardware-disk_bus").find('option').remove();
        if (typeof domain_id !== 'undefined'){
            url = '/api/v3/user/hardware/allowed/'+domain_id
        }else{
            url = '/api/v3/user/hardware/allowed'
        }
        api.ajax_async(url,'GET','').done(function(hardware) {
            if (hardware.virtualization_nested == true) {
                $(id+"hardware-virtualization_nested").iCheck('check').iCheck('update');
            } else {
                $(id+"hardware-virtualization_nested").iCheck('uncheck').iCheck('update');
            }
            $(id+" #hardware-interfaces").select2()

            $(id+" #hardware-interfaces").on('select2:select', function(e){
                var id = e.params.data.id;
                var option = $(e.target).children('[value='+id+']');
                option.detach();
                $(e.target).append(option).change();
              });
            $.each(hardware.interfaces,function(key, value)
            {
                $(id+" #hardware-interfaces").append('<option value="' + value.id + '">' + value.name + ' - ' + value.description + '</option>');
            });

            $(id+" #hardware-interfaces").html($(id+" #hardware-interfaces").children('option').sort(function(a, b){
                return a.text.localeCompare(b.text);
            }));

            $.each(hardware.videos,function(key, value)
            {
                $(id+" #hardware-videos").append('<option value="' + value.id + '">' + value.name + '</option>');
            });
            $.each(hardware.boot_order,function(key, value)
            {
                $(id+" #hardware-boot_order").append('<option value="' + value.id + '">' + value.name + '</option>');
            });
            $(id+' #hardware-boot_order option[value="'+default_boot+'"]').prop("selected",true);
            if(hardware.qos_id.length == 0){
                $(id+" #hardware-qos_id").append('<option value="unlimited">Unlimited</option>');
            }else{
                $.each(hardware.qos_disk,function(key, value)
                {
                    $(id+" #hardware-qos_id").append('<option value="' + value.id + '">' + value.name + '</option>');
                });
            }
            $.each(hardware.disk_bus,function(key, value)
            {
                $(id+" #hardware-disk_bus").append('<option value="' + value.id + '">' + value.name + '</option>');
            });

            if(hardware.quota == false){
                hardware.quota={'memory':128, 'vcpus':128, 'desktops_disk_size':500}
            }

            for (var i = 0.5; i <= hardware.quota.memory; i += 0.5) {
                $(id+" #hardware-memory").append('<option value="'+i+'">' + i +'</option>');
            }

            for (var i = 1; i <= hardware.quota.vcpus; i += 1) {
                $(id+" #hardware-vcpus").append('<option value="'+i+'">' + i +' vCPU</option>');
            }

            if($(id+" #disk_size").length != 0) {
                $(id+" #disk_size").find('option').remove();
                if(hardware.quota.desktops_disk_size <= 10){
                    for (var i = 1; i <= hardware.quota.desktops_disk_size; i += 1) {
                        $(id+" #disk_size").append('<option value="'+i+'">' + i +' GB</option>');
                    }
                }else{
                    $(id+" #disk_size").append('<option value=1>1 GB</option>');
                    $(id+" #disk_size").append('<option value=5>5 GB</option>');
                    for (var i = 10; i <= hardware.quota.desktops_disk_size; i += 5) {
                        $(id+" #disk_size").append('<option value="'+i+'">' + i +' GB</option>');
                    }
                }
            }

            $(id+" #reservables-vgpus").find('option').remove();
            if("reservables" in hardware && "vgpus" in hardware.reservables){
                $.each(hardware.reservables.vgpus,function(key, value)
                {
                    $(id+" #reservables-vgpus").append('<option value="' + value.id + '">' + value.name + ' - ' + value.description + '</option>');
                });
            }
        });
}

function setHardwareDomainIdDefaults(div_id,domain_id){
    api.ajax('/api/v3/domain/info/'+domain_id,'GET','').done(function(domain) {
        setHardwareDomainDefaults(div_id,domain)
    })
}

function setHardwareDomainDefaults(div_id,domain){
    $(div_id+' #forced_hyp').closest("div").remove();
    $(div_id+' #favourite_hyp').closest("div").remove();
    $(div_id+' #name_hidden').val(domain.name);
    if (div_id != '#modalAddDesktop') {
        $(div_id+' #name').val(domain.name);
    }
    $(div_id+' #description').val(domain.description);
    $(div_id+' #id').val(domain.id);
    $(div_id+' #guest_properties-credentials-username').val(domain["guest_properties"]["credentials"]["username"]);
    $(div_id+' #guest_properties-credentials-password').val(domain["guest_properties"]["credentials"]["password"]);
    setViewers('#modalEditDesktop',domain)
    if (domain.hardware.virtualization_nested) {
        $(div_id+' #hardware-virtualization_nested').prop('checked',true).iCheck('update');
    } else {
        $(div_id+' #hardware-virtualization_nested').prop('checked',false).iCheck('update');
    }
    $(div_id+' #hardware-videos option:selected').prop("selected", false);
    $(div_id+' #hardware-boot_order option:selected').prop("selected", false);
    $(div_id+' #hardware-disk_bus option:selected').prop("selected", false);

    $.each(domain.hardware.interfaces, function (key, value) {
        var optionText = $(div_id+' #hardware-interfaces').find("option[value='" + value.id + "']").eq(0).text();
        var newOption = new Option(optionText, value.id, true, true);
        $(div_id+' #hardware-interfaces').find("option[value='" + value.id + "']").remove()
        $(div_id+' #hardware-interfaces').append(newOption)
    });

    $(div_id+' #hardware-videos option[value="'+domain.hardware.videos[0]+'"]').prop("selected",true);
    $(div_id+' #hardware-disk_bus option[value="'+domain.hardware.disk_bus+'"]').prop("selected",true);

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

    $(div_id+"  #m-isos").empty().trigger('change')
    if("isos" in domain.hardware){
        domain.hardware.isos.forEach(function(data){
            var newOption = new Option(data.name, data.id, true, true);
                $(div_id+"  #m-isos").append(newOption).trigger('change');
        });
    }

    $(div_id+"  #m-floppies").empty().trigger('change')
    if("floppies" in domain.hardware){
        domain.hardware.floppies.forEach(function(data){
            var newOption = new Option(data.name, data.id, true, true);
                $(div_id+"  #m-floppies").append(newOption).trigger('change');
        });
    }

    $(div_id+' #reservables-vgpus option:selected').prop("selected", false);
    if(domain.hasOwnProperty("reservables") && "vgpus" in domain.reservables && domain.reservables.vgpus && domain.reservables.vgpus[0]){
        if ($(div_id+' #reservables-vgpus option[value="'+domain.reservables.vgpus[0]+'"]').length == 0) {
                $(div_id+" #reservables-vgpus").append('<option disabled value=' + domain.reservables.vgpus[0] + '>' + domain.reservables.vgpus[0] + '</option>')
        }
        $(div_id+' #reservables-vgpus option[value="'+domain.reservables.vgpus[0]+'"]').prop("selected",true);
    }else{
        $(div_id+' #reservables-vgpus option[value="None"]').prop("selected",true);
    }
}


function populate_tree_template(id){
    $(":ui-fancytree").fancytree("destroy")
    $(".template_tree").fancytree({

        extensions: ["table"],
        table: {
            indentation: 20,      // indent 20px per node level
            nodeColumnIdx: 2      // render the node title into the 2nd column
        },
        source: {
            url: "/api/v3/admin/desktops/tree_list/" + id,
            cache: false
        },
        lazyLoad: function(event, data) {
            data.result = $.ajax({
                url: "/api/v3/admin/desktops/tree_list/" + id,
                dataType: "json"
            });
        },
        selectMode: 3,
        renderColumns: function(event, data) {
            var node = data.node,
            $tdList = $(node.tr).find(">td");
            $tdList.eq(1).text(node.getIndexHier());
            // (index #2 is rendered by fancytree)
            $tdList.eq(3).text(node.data.user);
            $tdList.eq(4).text(node.data.kind);
            $tdList.eq(5).text(node.data.category);
            $tdList.eq(6).text(node.data.group);
        }
    });

}

function setHardwareDomainDefaultsDetails(domain_id,item){
    if (item == "domain"){
        ajaxUrl = "/api/v3/domain/hardware/"+domain_id
    } else if (item == "deployment"){
        ajaxUrl = "/api/v3/deployment/hardware/"+domain_id
    }
    $.ajax({
        type: "GET",
        url: ajaxUrl,
        success: function (data) {
            div_id='#hardware-'+domain_id
            div_id = div_id.replaceAll('.', '\\.')
            div_id = div_id.replaceAll('=', '\\=')
            $(div_id+" #vcpu").html(data.hardware.vcpus+' CPU(s)');
            $(div_id+" #ram").html((data.hardware.memory).toFixed(2)+'GB');
            if(data.reservables){
                $(div_id+" #gpu").html(data.reservable_name);
                $(div_id+" #gpu").closest("tr").show();
           }else{
                $(div_id+" #gpu").closest("tr").hide();
            }
            $(div_id+" #net").html(data.interfaces_names.join(', '));
            $(div_id+" #video").html(data.video_name);
            $(div_id+" #boot").html(data.boot_name);
            $(div_id+" #disk_bus").html(data.hardware.disk_bus);
            if(data['forced_hyp']){
                $(div_id+" #forced_hyp").html(data['forced_hyp']);
                $(div_id+" #forced_hyp").closest("tr").show();
            }else{
                $(div_id+" #forced_hyp").closest("tr").hide();
            }
            if(data['favourite_hyp']){
                $(div_id+" #favourite_hyp").html(data['favourite_hyp']);
                $(div_id+" #favourite_hyp").closest("tr").show();
            }else{
                $(div_id+" #favourite_hyp").closest("tr").hide();
            }
            if (data.kind == 'desktop') {
                populate_tree_template(data.origin ? data.origin : data.id);
            }
        }
    });
}

function setDomainStorage(domain_id) {
    storage_table = $("#table-storage-" + domain_id.replaceAll('.', '\\.')).DataTable({
        "ajax": {
            "url": "/api/v3/admin/domain/storage/" + domain_id,
            "contentType": "application/json",
            "type": 'GET'
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "deferRender": true,
        'searching': false,
        'paging': false,
        "columns": [
            { "data": "id" },
            { 'data': 'actual_size' },
            { 'data': 'virtual_size' }
        ],
        "columnDefs": [
            {
                "targets": 0,
                "render": function ( data, type, full, meta ) {
                    return '<a href="/isard-admin/admin/domains/render/Storage?searchStorageId='+ full.id +'">'+ full.id +'</a>'
                }
            },
            {
                "targets": 1,
                "render": function (data, type, full, meta) {
                    return full.actual_size.toFixed(1)
                }
            },
            {
                "targets": 2,
                "render": function (data, type, full, meta) {
                    return full.virtual_size.toFixed(1)
                }
            }
        ],
        "order": [[1, 'desc']]
    })
}