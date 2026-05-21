// Dropdown ceilings (1 TB RAM, 128 vCPU, 2 TB disk) with coarsening steps so
// the option list stays bounded even when the quota is the "unlimited" sentinel.
var MEMORY_TIERS = [
    { from: 0.5, to: 4, step: 0.5 },
    { from: 5, to: 16, step: 1 },
    { from: 18, to: 32, step: 2 },
    { from: 36, to: 64, step: 4 },
    { from: 72, to: 128, step: 8 },
    { from: 144, to: 256, step: 16 },
    { from: 288, to: 512, step: 32 },
    { from: 576, to: 1024, step: 64 }
];
var VCPU_TIERS = [
    { from: 1, to: 16, step: 1 },
    { from: 18, to: 32, step: 2 },
    { from: 36, to: 64, step: 4 },
    { from: 72, to: 128, step: 8 }
];
var DISK_TIERS = [
    { from: 1, to: 16, step: 1 },
    { from: 18, to: 32, step: 2 },
    { from: 36, to: 64, step: 4 },
    { from: 72, to: 128, step: 8 },
    { from: 144, to: 256, step: 16 },
    { from: 288, to: 512, step: 32 },
    { from: 576, to: 1024, step: 64 },
    { from: 1152, to: 2048, step: 128 }
];

function buildTieredOptions(quotaMax, tiers) {
    if (quotaMax == null || !(quotaMax > 0)) return [];
    var result = [];
    for (var t = 0; t < tiers.length; t++) {
        var tier = tiers[t];
        var limit = Math.min(tier.to, quotaMax);
        if (tier.from > limit) break;
        for (var v = tier.from; v <= limit + 1e-9; v += tier.step) {
            result.push(+v.toFixed(2));
        }
    }
    return result;
}

// Snap a non-tier-aligned legacy value to the nearest dropdown option so the
// form submits a valid value. Ties break low.
function selectNearestOption(selector, target) {
    if (target == null || !isFinite(target)) return;
    var $opts = $(selector + ' option');
    if ($opts.length === 0) return;
    var bestVal = null;
    var bestDiff = Infinity;
    $opts.each(function () {
        var v = parseFloat($(this).val());
        if (isNaN(v)) return;
        var diff = Math.abs(v - target);
        if (diff < bestDiff) {
            bestDiff = diff;
            bestVal = v;
        }
    });
    if (bestVal !== null) {
        $(selector + ' option[value="' + bestVal + '"]').prop('selected', true);
    }
}

function setHardwareOptions(id,default_boot,domain_id,callback){
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
            url = '/api/v4/item/user/get-allowed-hardware/'+domain_id
        }else{
            url = '/api/v4/item/user/get-allowed-hardware'
        }
        $.ajax({
            type: 'GET',
            url: url,
            accept: 'application/json',
        }).done(function(hardware) {
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

            var memoryOpts = buildTieredOptions(hardware.quota.memory, MEMORY_TIERS);
            for (var mi = 0; mi < memoryOpts.length; mi++) {
                $(id+" #hardware-memory").append('<option value="'+memoryOpts[mi]+'">' + memoryOpts[mi] +'</option>');
            }

            var vcpuOpts = buildTieredOptions(hardware.quota.vcpus, VCPU_TIERS);
            for (var vi = 0; vi < vcpuOpts.length; vi++) {
                $(id+" #hardware-vcpus").append('<option value="'+vcpuOpts[vi]+'">' + vcpuOpts[vi] +' vCPU</option>');
            }

            if($(id+" #disk_size").length != 0) {
                $(id+" #disk_size").find('option').remove();
                var diskOpts = buildTieredOptions(hardware.quota.desktops_disk_size, DISK_TIERS);
                for (var di = 0; di < diskOpts.length; di++) {
                    $(id+" #disk_size").append('<option value="'+diskOpts[di]+'">' + diskOpts[di] +' GB</option>');
                }
            }

            // Rebuild the vGPU control from scratch. It is enhanced with select2
            // (like #hardware-interfaces) so the list is click-to-toggle (no
            // Ctrl), searchable and scrollable instead of a cramped native
            // multi-select; destroy any previous instance before repopulating.
            if($(id+" #reservables-vgpus").hasClass('select2-hidden-accessible')){
                $(id+" #reservables-vgpus").select2('destroy');
            }
            $(id+" #reservables-vgpus").find('option,optgroup').remove();
            if("reservables" in hardware && "vgpus" in hardware.reservables){
                // A desktop may carry several vGPU profiles but they must all run
                // on ONE hypervisor. Group the options by hypervisor name so the
                // admin sees which profiles are co-locatable; a profile enabled on
                // several hypervisors appears under each. Each option carries its
                // full hypervisor list so selection can be hard-restricted to one.
                var byHyp = {};
                var ungrouped = [];
                $.each(hardware.reservables.vgpus, function(key, value){
                    var hyps = value.hypervisors || [];
                    if(!hyps.length){ ungrouped.push(value); return; }
                    $.each(hyps, function(i, h){ (byHyp[h] = byHyp[h] || []).push(value); });
                });
                // NUMA nodes a card of any reservable occupies on hypervisor h; a
                // server is "multi-socket" when this spans >1 node (single-socket /
                // all-in-one stay a plain per-hypervisor group, as before).
                function hypNodes(h){
                    var s = {};
                    (byHyp[h]||[]).forEach(function(v){
                        ((v.numa_by_hypervisor||{})[h]||[]).forEach(function(n){ s[n]=true; });
                    });
                    return Object.keys(s).map(Number).sort(function(a,b){return a-b;});
                }
                // Each option carries its hypervisor list (cross-server restrict) and
                // its per-hypervisor NUMA nodes (same-socket hint), both informational.
                function optHtml(value){
                    return '<option value="' + value.id + '" data-hyps=\'' +
                        JSON.stringify(value.hypervisors || []) + '\' data-numa=\'' +
                        JSON.stringify(value.numa_by_hypervisor || {}) + '\'>' +
                        value.name + ' - ' + value.description + '</option>';
                }
                Object.keys(byHyp).sort().forEach(function(h){
                    var nodes = hypNodes(h);
                    if(nodes.length > 1){
                        // Multi-socket server: one optgroup per NUMA socket so the
                        // admin can pick same-socket cards. Each reservable is listed
                        // once, under its LOWEST socket on this host (annotated with
                        // any other sockets it can also reach) -- no duplication, so
                        // no accidental double-select.
                        var bySock = {};
                        byHyp[h].forEach(function(value){
                            var vn = ((value.numa_by_hypervisor||{})[h]||[]).slice().sort(function(a,b){return a-b;});
                            var primary = vn.length ? vn[0] : -1;
                            (bySock[primary] = bySock[primary] || []).push({v:value, vn:vn});
                        });
                        Object.keys(bySock).map(Number).sort(function(a,b){return a-b;}).forEach(function(s){
                            var label = s >= 0 ? (h + ' · NUMA ' + s) : (h + ' · NUMA (unknown)');
                            var $g = $('<optgroup label="' + label + '">');
                            bySock[s].forEach(function(item){
                                var $o = $(optHtml(item.v));
                                if(item.vn.length > 1){ $o.text($o.text() + ' (NUMA ' + item.vn.join('/') + ')'); }
                                $g.append($o);
                            });
                            $(id+" #reservables-vgpus").append($g);
                        });
                    } else {
                        var $g = $('<optgroup label="' + h + '">');
                        byHyp[h].forEach(function(value){ $g.append(optHtml(value)); });
                        $(id+" #reservables-vgpus").append($g);
                    }
                });
                ungrouped.forEach(function(value){
                    $(id+" #reservables-vgpus").append(optHtml(value));
                });
                // Hard-restrict: once a profile is chosen, disable any profile not
                // hostable on a hypervisor common to the whole selection, then
                // tell select2 to re-render so the greyed-out options show.
                $(id+" #reservables-vgpus").off('change.vgpurestrict').on('change.vgpurestrict', function(){
                    var selected = $(this).val() || [];
                    var common = null;
                    selected.forEach(function(v){
                        var hyps = $(this).find('option[value="'+v+'"]').first().data('hyps') || [];
                        var s = {}; hyps.forEach(function(h){ s[h]=true; });
                        if(common === null){ common = s; }
                        else { var n={}; Object.keys(common).forEach(function(h){ if(s[h]) n[h]=true; }); common = n; }
                    }.bind(this));
                    var hasCommon = common && Object.keys(common).length;
                    $(this).find('option').each(function(){
                        if($(this).val() === 'None'){ return; }
                        if(!selected.length || !hasCommon){ $(this).prop('disabled', false); return; }
                        var hyps = $(this).data('hyps') || [];
                        var ok = hyps.some(function(h){ return common[h]; });
                        $(this).prop('disabled', !ok);
                    });
                    // Same-socket performance hint (informational; NUMA never
                    // disables a card). On a multi-socket common server, is there a
                    // NUMA node every selected profile has a card on?
                    var $sel = $(this);
                    var hint = '';
                    if(selected.length >= 2 && hasCommon){
                        var okNode = null, anyMulti = false;
                        Object.keys(common).forEach(function(h){
                            var union = {};
                            $sel.find('option').each(function(){
                                var nm = $(this).data('numa') || {};
                                (nm[h]||[]).forEach(function(n){ union[n]=true; });
                            });
                            if(Object.keys(union).length <= 1){ return; }
                            anyMulti = true;
                            var inter = null;
                            selected.forEach(function(v){
                                var nm = $sel.find('option[value="'+v+'"]').first().data('numa') || {};
                                var s = {}; (nm[h]||[]).forEach(function(n){ s[n]=true; });
                                if(inter === null){ inter = s; }
                                else { var n2={}; Object.keys(inter).forEach(function(k){ if(s[k]) n2[k]=true; }); inter=n2; }
                            });
                            if(inter && Object.keys(inter).length && okNode === null){
                                okNode = Object.keys(inter).map(Number).sort(function(a,b){return a-b;})[0];
                            }
                        });
                        if(okNode !== null){
                            hint = '<span class="text-success"><i class="fa fa-check-circle"></i> Same NUMA socket possible (node '+okNode+') — cards can share a socket, best memory bandwidth.</span>';
                        } else if(anyMulti){
                            hint = '<span class="text-warning"><i class="fa fa-exclamation-triangle"></i> Different NUMA sockets — the desktop still starts, but cross-socket memory access is slower.</span>';
                        }
                    }
                    $(id+" #vgpu-numa-hint").html(hint);
                    if($(this).hasClass('select2-hidden-accessible')){
                        $(this).trigger('change.select2');
                    }
                });
                // Enhance with select2: click-to-toggle, searchable, scrollable.
                $(id+" #reservables-vgpus").select2({
                    width: '100%',
                    closeOnSelect: false,
                    placeholder: 'Select GPU profile(s)',
                });
            }
            if (callback) {
                callback();
            }
        });
}

function setHardwareDomainIdDefaults(div_id,domain_id){
    $.ajax({
        type: 'GET',
        url: '/api/v4/item/desktop/'+domain_id+'/get-info',
        accept: 'application/json',
    }).done(function(domain) {
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
    var credentials = ((domain || {}).guest_properties || {}).credentials || {};
    $(div_id+' #guest_properties-credentials-username').val(credentials.username || '');
    $(div_id+' #guest_properties-credentials-password').val(credentials.password || '');
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

    // Snap legacy non-tier-aligned values to the nearest option, not the first.
    selectNearestOption(div_id+' #hardware-memory', parseFloat(domain.hardware.memory));
    selectNearestOption(div_id+' #hardware-vcpus', parseInt(domain.hardware.vcpus, 10));

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
    var domVgpus = (domain.reservables && domain.reservables.vgpus) || [];
    if(domVgpus.length){
        // Preselect EVERY assigned profile (a desktop may have several).
        domVgpus.forEach(function(vgpu){
            if ($(div_id+' #reservables-vgpus option[value="'+vgpu+'"]').length == 0) {
                $(div_id+" #reservables-vgpus").append('<option disabled value="' + vgpu + '">' + vgpu + '</option>')
            }
            $(div_id+' #reservables-vgpus option[value="'+vgpu+'"]').prop("selected",true);
        });
    }else{
        $(div_id+' #reservables-vgpus option[value="None"]').prop("selected",true);
    }
    // Plain 'change' so select2 re-renders the selection AND the hard-restrict
    // handler (namespaced on change) runs.
    $(div_id+' #reservables-vgpus').trigger('change');
}

function setHardwareDomainDefaultsDetails(domain_id,item){
    if (item == "domain"){
        ajaxUrl = "/api/v4/admin/item/domain/hardware/"+domain_id
    } else if (item == "deployment"){
        ajaxUrl = "/api/v4/item/deployment/"+domain_id+"/hardware"
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
            let interfaces = []
            $.each(data.hardware.interfaces, function (key, value) {
                if (item == "domain") {
                    interfaces.push(`${value.name} (${value.mac})`)
                } else if (item == "deployment") {
                    interfaces.push(value.name)
                }
            })
            $(div_id+" #net").html(interfaces.join(', '));
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
        }
    });
}

function setDomainStorage(domain_id) {
    storage_table = $("#table-storage-" + domain_id.replaceAll('.', '\\.')).DataTable({
        "ajax": {
            "url": "/api/v4/admin/item/domain/storage/" + domain_id,
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
                    // actual_size/virtual_size are GiB floats; render in human
                    // units so sub-GiB disks don't collapse to "0.0". Keep the
                    // raw value for sorting.
                    if (type !== 'display') return full.actual_size || 0;
                    return formatBytes((full.actual_size || 0) * 1024 * 1024 * 1024);
                }
            },
            {
                "targets": 2,
                "render": function (data, type, full, meta) {
                    if (type !== 'display') return full.virtual_size || 0;
                    return formatBytes((full.virtual_size || 0) * 1024 * 1024 * 1024);
                }
            }
        ],
        "order": [[1, 'desc']]
    })
}