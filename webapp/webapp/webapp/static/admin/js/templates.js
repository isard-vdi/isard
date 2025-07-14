/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var href = location.href;
url=href.match(/([^\/]*)\/*$/)[1];
if (url!="Desktops") {
    kind='template'
} else {
    $('#global_actions').css('display','block');
    kind='desktop'
}

// Sort by Last Access in Desktops table
order=15

columns= [
    {
        "className": 'details-control',
        "orderable": false,
        "data": null,
        "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
    },
    { "data": "icon" },
    { "data": "name"},
    { "data": "description"},
    { "data": "status"},
    { "data": null, "className": 'viewer',},
    { "data": "ram"},
    { "data": "create_dict.hardware.vcpus", "width": "10px"},
    { "data": "user_name"},
    { "data": "category_name"},
    { "data": "group_name"},
    { "data": "server", "width": "10px", "defaultContent":"-"},
    { "data": "hyp_started", "width": "100px"},
    { "data": "favourite_hyp", "width": "100px"},
    { "data": "forced_hyp", "width": "100px"},
    { "data": "accessed", 'defaultContent': '' },
    {
        "className": 'text-center',
        "data": null,
        "orderable": false,
        "defaultContent": '<input type="checkbox" class="form-check-input"></input>'
    },
    { "data": "id", "visible": false},
]

columnDefs = [
    {
        "targets": 1,
        "render": function ( data, type, full, meta ) {
            img_url = location.protocol+'//' + document.domain + ':' + location.port + full.image.url
            if( ! "booking_id" in full ){
                booking_id=false
            }else{
                booking_id=full.booking_id
            }
            return  renderFailed(full.status, full.create_dict.reservables) + renderBooking(full.create_dict.reservables, booking_id) + "<img src='"+img_url+"' width='50px'>"
        }
    },{
        "targets": 4,
        "render": function (data, type, full, meta) {
            return renderStatus(full)
        }
    },{
        "targets": 5,
        "width": "100px",
        "render": function (data, type, full, meta) {
            return renderAction(full) + renderDisplay(full)
        }
    },{
        "targets": 6,
        "width": "100px",
        "render": function (data, type, full, meta) {
            return (full.create_dict.hardware.memory / 1024 / 1024).toFixed(2) + "GB"
        }
    },{
        "targets": 11,
        "render": function (data, type, full, meta) {
            if('server' in full){
                if(full["server"] == true){
                    return 'SERVER';
                }else{
                    return '-';
                }
            }else{
                return '-';
            }
        }
    },{
        "targets": 12,
        "render": function (data, type, full, meta) {
            if('hyp_started' in full && full.hyp_started != ''){
                return full.hyp_started;
            } else {
                return '-'
            }
        }
    },{
        "targets": 13,
        "render": function (data, type, full, meta) {
            if('favourite_hyp' in full && full.favourite_hyp != ''){ 
                return full.favourite_hyp;
            } else {
                return '-'
            }
        }
    },{
        "targets": 14,
        "render": function (data, type, full, meta) {
            if('forced_hyp' in full && full.forced_hyp != ''){
                return full.forced_hyp;
            } else {
                return '-'
            }
        }
    },{
        "targets": 15,
        "render": function (data, type, full, meta) {
            if ( type === 'display' || type === 'filter' ) {
                return moment.unix(full.accessed).fromNow()
            }
            return full.accessed
        }
    }
]

// Templates table render
    // Remove Select column (used for bulk actions)
    columns.splice(16, 1)
    // Remove Server column
    columns.splice(11, 1)
    // Remove Started Hyper column
    columns.splice(11, 1)
    // Remove Status, Action, Memory(GB) and VCPUs columns
    columns.splice(4, 4)
    // Add Enabled, Derivates and Shared columns
    columns.splice(
        9,
        0,
        {
            "data": 'enabled',
            "className": 'text-center',
            "orderable": false,
            "defaultContent": '<input type="checkbox" class="form-check-input" checked></input>'
        },
        {"data": "derivates", "width": "2px"},
        {"defaultContent": '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button>'},
    );
    // Remove custom rendering of Status, Action, Memory(GB), Server and Started Hyper columns
    columnDefs.splice(1, 5)
    // Change custom render target of Favourite Hyper, Forced Hyper and Last Access columns
    columnDefs[1]["targets"]=7
    columnDefs[2]["targets"]=8
    columnDefs[3]["targets"]=12
    // Add rendering of Enabled column 
    columnDefs.push({
        "targets": 9,
        "render": function ( data, type, full, meta ) {
            if( full.enabled ){
                return '<input id="chk-enabled" type="checkbox" class="form-check-input" checked></input><span style="display: none;">' + data + '</span>'
            }else{
                return '<input id="chk-enabled" type="checkbox" class="form-check-input"></input><span style="display: none;">' +data + '</span>'
            }
        }
    })
    // Sort by Last Access in Templates table
    order = 12;

    $.fn.dataTable.ext.search.push(function (settings, searchData, index, rowData, counter ) {
            search_val = $('.panel_toolbox .btn-disabled').attr('view')
            if (search_val == 'false') {
                return true;
            }
            else if (
               searchData[9] == search_val
            ) {
                return true;
            }
            return false;
    });

function getGroupParam() {
    return window.location.href.slice(window.location.href.indexOf('?') + 1).split('searchDomainId=')[1];
}

$(document).ready(function() {
    $template_domain = $(".template-detail-domain");
    $admin_template_domain = $(".admin-template-detail-domain");

    var stopping_timer=null
    modal_add_desktops = $('#modal_add_desktops').DataTable()
    initalize_modal_all_desktops_events()

    $("#modalDeleteTemplate #send").on('click', function(e){
        var form = $('#modalDeleteTemplateForm');
        formdata = form.serializeObject()
        template_id = formdata.id
            var notice = new PNotify({
                text: 'Deleting selected item(s)...',
                hide: false,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })
            $.ajax({
                type: 'DELETE',
                url: '/api/v3/admin/templates/delete/'+template_id,
                contentType: 'application/json',
                error: function(data) {
                    notice.update({
                        title: 'ERROR deleting items',
                        text: data.responseJSON && data.responseJSON.description ? data.responseJSON.description : 'Something went wrong.',
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                },
                success: function(data) {
                    $('form').each(function() {
                        this.reset()
                    });
                    $('.modal').modal('hide');
                    domains_table.ajax.reload();
                    notice.update({
                        title: 'Deleted',
                        text: 'Item(s) deleted successfully',
                        hide: true,
                        delay: 2000,
                        icon: 'fa fa-' + data.icon,
                        opacity: 1,
                        type: 'success'
                    })
                }
            })
    });

    $("#modalDuplicateTemplate #send").on('click', function(e){
        var form = $('#modalDuplicateTemplateForm');
        form.parsley().validate();
        if (form.parsley().isValid()){
            data=$('#modalDuplicateTemplateForm').serializeObject();
            data=replaceAlloweds_arrays('#modalDuplicateTemplateForm #alloweds-add',data)
            sent_data = {"name": data.name,
                        "description": data.description,
                        "enabled": $('#modalDuplicateTemplateForm #enabled').prop('checked'),
                        "allowed": data.allowed,
                        ...("user_id" in data) && {"user_id": data["user_id"]}}
            var notice = new PNotify({
                text: 'Duplicating template...',
                hide: false,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })
            $.ajax({
                type: 'POST',
                url: '/api/v3/template/duplicate/'+data.id,
                data: JSON.stringify(sent_data),
                contentType: 'application/json',
                error: function(data) {
                    notice.update({
                        title: 'ERROR duplicating template',
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                },
                success: function(data) {
                    domains_table.ajax.reload()
                    $('form').each(function() { this.reset() });
                    $('.modal').modal('hide');
                    notice.update({
                        title: 'Duplicated',
                        text: 'Template duplicated successfully',
                        hide: true,
                        delay: 2000,
                        icon: 'fa fa-' + data.icon,
                        opacity: 1,
                        type: 'success'
                    })
                }
            })
        }
    });

    // Setup - add a text input to each footer cell
    $('#domains tfoot th').each( function () {
        var title = $(this).text();
        if (['', 'Icon', 'Action', 'Enabled'].indexOf(title) == -1){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );

    domains_table= $('#domains').DataTable({
        scrollY: false,
        scrollX: false,
        ajax: {
            url: "/admin/domains",
            type: "POST",
            contentType: 'application/json',
            dataSrc : "",
            data: function () {
                return JSON.stringify({ kind: "template" })
            } 
        },
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "deferRender": true,
        "paging": true,
        "columns": columns,
        "order": [[order, 'des']],
        "columnDefs": columnDefs,
        "rowCallback": function (row, data) {
            if('server' in data){
                if(data['server'] == true){
                    $(row).css("background-color", "#f7eac6");
                }else{
                    $(row).css("background-color", "#ffffff");
                }
            }
        }
    } );

    // Apply the search
    domains_table.columns().every( function () {
        var that = this;

        $( 'input', this.footer() ).on( 'keyup change', function () {
            if ( that.search() !== this.value ) {
                that
                    .search( this.value )
                    .draw();
            }
        } );
    } );

    let searchDomainId = getGroupParam()
    if (searchDomainId) {
        domains_table.search(searchDomainId).draw()
    }

    $('.btn-search-template').on('click', function () {
        initDomainSearchModal();
    });

    $("#modalSearchDomain").off('click', '.btn-copy').on('click', '.btn-copy', function() {
        const text = $(this).data('copy-value') || '';
        navigator.clipboard.writeText(text).then(() => {
            new PNotify({ title: 'Copied to Clipboard', text: `"${text}" has been copied to clipboard.`, type: 'success', delay: 2000 });
        }).catch(() => {
            new PNotify({ title: 'ERROR', text: 'Failed to copy to clipboard.', type: 'error', delay: 2000 });
        });
    });

    $("#modalSearchTemplate").off('click', '.btn-copy').on('click', '.btn-copy', function() {
        const text = $(this).data('copy-value') || '';
        navigator.clipboard.writeText(text).then(() => {
            new PNotify({ title: 'Copied to Clipboard', text: `"${text}" has been copied to clipboard.`, type: 'success', delay: 2000 });
        }).catch(() => {
            new PNotify({ title: 'ERROR', text: 'Failed to copy to clipboard.', type: 'error', delay: 2000 });
        });
    });

    $('.btn-disabled').on('click', function(e) {
        if ($('.btn-disabled').attr('view')=='false') {
            $('.btn-disabled #view-disabled').show();
            $('.btn-disabled #hide-disabled').hide();
            $('.btn-disabled').attr('view', 'true')
        }
        else {
            $('.btn-disabled #view-disabled').hide();
            $('.btn-disabled #hide-disabled').show();
            $('.btn-disabled').attr('view', 'false')
        }
    })
    $('.panel_toolbox .btn-disabled').click(function () {
        domains_table.draw();
    });

    domains_table.on( 'click', 'tbody tr', function (e) {
        if (kind =='desktop') {
            toggleRow(this, e);
        }
     });


    $('#domains').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = domains_table.row( tr );
        domain_id=row.data().id

        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
                // Open this row
                row.child( addDomainDetailPannel(row.data()) ).show();
                $('#status-detail-'+domain_id).html(row.data().detail);
                actionsDomainDetail();
                setDomainDetailButtonsStatus(domain_id,row.data().status,row.data().server)
                setDomainHotplug(domain_id);
                setHardwareDomainDefaultsDetails(domain_id, 'domain');
                setDomainStorage(domain_id)
                setAlloweds_viewer('#alloweds-'+domain_id,domain_id);
            
                // Close other rows
                if (domains_table.row('.shown').length) {
                    $('.details-control', domains_table.row('.shown').node()).click();
                }
                tr.addClass('shown');
        }
    } );

    $('#domains').find(' tbody').on( 'click', 'input', function () {
        var pk=domains_table.row( $(this).parents('tr') ).id();
        var checkbox = $(this)
        var template_enabled = domains_table.row( $(this).parents('tr') ).data().enabled
        switch($(this).attr('id')){
            case 'chk-enabled':
                if ($(this).is(":checked")){
                    enabled=true
                }else{
                    enabled=false
                }
                new PNotify({
                    title: 'This template will be ' + (enabled==true? 'enabled': 'disabled') ,
                        text: "Are you sure you want to " + (enabled==true? 'enable': 'disable') + " this template?" + (enabled ? '' : ' All the temporal desktops (if any) derivated from this template will be deleted'),
                        hide: false,
                        opacity: 0.9,
                        confirm: {
                            confirm: true
                        },
                        buttons: {
                            closer: false,
                            sticker: false
                        },
                        history: {
                            history: false
                        },
                        addclass: 'pnotify-center'
                    }).get().on('pnotify.confirm', function() {
                        $.ajax({
                            type: "PUT",
                            url:"/api/v3/template/update",
                            data: JSON.stringify({id:pk, enabled:enabled}),
                            contentType: "application/json",
                            accept: "application/json",
                            error: function(data) {
                                new PNotify({
                                    title: "ERROR enabling/disabling template",
                                    text: data.responseJSON.description,
                                    hide: true,
                                    delay: 3000,
                                    icon: 'fa fa-alert-sign',
                                    opacity: 1,
                                    type: 'error'
                                })
                                domains_table.ajax.reload()
                            },
                            success: function(data) {
                                new PNotify({
                                    title: "Template " + (data.enabled? 'enabled': 'disabled'),
                                    text: "",
                                    hide: true,
                                    delay: 1000,
                                    icon: 'fa fa-success',
                                    opacity: 1,
                                    type: 'success'
                                });
                                domains_table.ajax.reload()
                            }
                        });
                    }).on('pnotify.cancel', function() {
                        checkbox.prop("checked", template_enabled)
                        domains_table.ajax.reload()
                    });
            break;
        }
    })

    adminShowIdCol(domains_table)

    renderBooking = (reservables, booking_id) => {
        if (!reservables || reservables.length == 0 || !reservables.vgpus || reservables.vgpus.length == 0){
            return ' '
        } else {
            var color, tooltip = {}
            var sort_order = '3'
            if( booking_id == false || booking_id == null){
                color="slategrey"
                tooltip='This desktop needs to be booked'
                sort_order='0'
            } else {
                color='mediumseagreen'
                tooltip='This desktop is now in booking time'
                sort_order='2'
            }
        style = "color:"+color+"; position:absolute; margin-top:-5px; margin-left: -15px; text-shadow: 0 0 1px grey"
        return '<div style=display:none>'+sort_order+'</div><i data-toggle="tooltip" title="'+tooltip+'" class="fa fa-calendar" aria-hidden="true" style="'+style+'"></i>'
        }
    }

    renderFailed = (status, reservables) => {
        var margin = '15px'
        if (status !== 'Failed') {
            return ' '
        } else if (!reservables || reservables.length == 0 || !reservables.vgpus || reservables.vgpus.length == 0){
            margin = '-5px'
        }
        var style = "color: red; position:absolute; margin-top:" + margin +"; margin-left: -15px; text-shadow: 0 0 1px grey"
        return '<div style=display:none>2</div><i data-toggle="tooltip" title="Due to an error this template isn\'t working properly, check its status detailed info to see the reason" class="fa fa-exclamation-triangle" aria-hidden="true" style="'+style+'"></i>'
    }

	// DataTable buttons
    $('#domains tbody').on( 'click', 'button', function () {
        var data = domains_table.row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
            case 'btn-alloweds':
                modalAllowedsFormShow('domains',data)
                break;
        }
    });
    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
})
function socketio_on(){
    socket.on(kind+'_delete', function(data){
        var data = JSON.parse(data);
        var row = domains_table.row('#'+data.id).remove().draw();
        new PNotify({
                title: kind+" deleted",
                text: kind+" "+data.name+" has been deleted",
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
        });
    });

    socket.on ('result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $('.modal').modal('hide');
        }
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
    });

    socket.on('add_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $("#modalAddFromBuilder #modalAdd")[0].reset();
            $("#modalAddFromBuilder").modal('hide');
            $("#modalAddFromMedia #modalAdd")[0].reset();
            $("#modalAddFromMedia").modal('hide');
            $("#modalTemplateDesktop #modalTemplateDesktopForm")[0].reset();
            $("#modalTemplateDesktop").modal('hide');
        }
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
    });

    socket.on('adds_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $("#modalAddDesktop #modalAdd")[0].reset();
            $("#modalAddDesktop").modal('hide');
        }
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
    });

    socket.on('edit_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $("#modalEdit")[0].reset();
            $("#modalEditDesktop").modal('hide');
            $("#modalBulkEditForm")[0].reset();
            $("#modalBulkEdit").modal('hide');
        }
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
    });
}

function actionsDomainDetail(){

    $('.btn-edit').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        $("#modalEdit")[0].reset();
        setHardwareOptions('#modalEditDesktop','hd',pk);
        setHardwareDomainIdDefaults('#modalEditDesktop',pk);
        setMedia_add('#modalEditDesktop #media-block')
        $('#modalEditDesktop').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalEdit').parsley();
    });

    $('.btn-xml').on('click', function () {
            var pk=$(this).closest("[data-pk]").attr("data-pk");
            $("#modalEditXmlForm")[0].reset();
            $('#modalEditXml').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            $('#modalEditXmlForm #id').val(pk);
            $.ajax({
                type: "GET",
                url:"/api/v3/admin/domains/xml/" + pk,
                success: function(data)
                {
                    $('#modalEditXmlForm #xml').val(data);
                }
            });
    });

    $('.btn-server').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        $("#modalServerForm")[0].reset();
        $('#modalServer').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalServerForm #id').val(pk);
        $.ajax({
            type: "POST",
            url:"/api/v3/admin/table/domains",
            data: JSON.stringify({
                'id': pk,
                'pluck': "server"
            }),
            contentType: 'application/json',
            success: function(data)
            {
                if(data.server == true){
                    $('#modalServerForm #server').iCheck('check').iCheck('update');
                }else{
                    $('#modalServerForm #server').iCheck('unckeck').iCheck('update');
                }
            }
        });
    });

    $('.btn-owner').on('click', function () {
        var pk = $(this).closest("[data-pk]").attr("data-pk");
        $("#modalChangeOwnerDomainForm")[0].reset();
        $('#modalChangeOwnerDomain').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalChangeOwnerDomainForm #id').val(pk);
        $("#new_owner").val("");
        if ($("#new_owner").data('select2')) {
            $("#new_owner").select2('destroy');
        }
        $('#new_owner').select2({
            placeholder: "Type at least 2 letters to search.",
            minimumInputLength: 2,
            dropdownParent: $('#modalChangeOwnerDomain'),
            ajax: {
                type: "POST",
                url: '/admin/users/search',
                dataType: 'json',
                contentType: "application/json",
                delay: 250,
                data: function (params) {
                    return JSON.stringify({
                        term: params.term,
                    });
                },
                processResults: function (data) {
                    return {
                        results: $.map(data, function (item, i) {
                            return {
                                text: item.name + '[' + item['uid'] + '] ',
                                id: item.id
                            }
                        })
                    };
                }
            },
        });
    });

    $("#modalChangeOwnerDomain #send").off('click').on('click', function (e) {
        var form = $('#modalChangeOwnerDomainForm');
        form.parsley().validate();
        if (form.parsley().isValid()) {
            data = form.serializeObject();
            let pk = $('#modalChangeOwnerDomainForm #id').val()
            $.ajax({
                type: "PUT",
                url: `/api/v3/template/owner/${pk}/${data['new_owner']}`,
                contentType: 'application/json',
                success: function (data) {
                    $('form').each(function () { this.reset() });
                    $('.modal').modal('hide');
                    new PNotify({
                        title: "Owner changed succesfully",
                        text: "",
                        hide: true,
                        delay: 4000,
                        icon: 'fa fa-success',
                        opacity: 1,
                        type: "success"
                    });
                    domains_table.ajax.reload();
                },
                error: function (data) {
                    new PNotify({
                        title: "ERROR",
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 15000,
                        opacity: 1
                    });
                }
            });
        };
    });

    $('.btn-delete-template').on('click', function () {
        $('#modalDeleteTemplate #manager-warning').hide();
        $('#modalDeleteTemplate p').show();
        $('#modalDeleteTemplate #send').prop('disabled', false);
        $('#modalDeleteTemplate #send').attr('title', '');
    
        var pk = $(this).closest("[data-pk]").attr("data-pk")
        $('#modalDeleteTemplate').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalDeleteTemplateForm #id').val(pk);
        populate_tree_template_delete(pk);
    });

$('.btn-duplicate-template').on('click', function () {
    if($('.quota-templates .perc').text() >=100){
        new PNotify({
            title: "Quota for creating templates full.",
            text: "Can't create another template, quota full.",
            hide: true,
            delay: 3000,
            icon: 'fa fa-alert-sign',
            opacity: 1,
            type: 'error'
        });
    }else{
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        setDefaultsTemplate(pk);
        populate_users();
        $('#modalDuplicateTemplate').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        setAlloweds_add('#modalDuplicateTemplate #alloweds-add');
    }
});


    $('.btn-jumperurl').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        $("#modalJumperurlForm")[0].reset();
        $('#modalJumperurlForm #id').val(pk);
        $('#modalJumperurl').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        // setModalUser()
        // setQuotaTableDefaults('#edit-users-quota','users',pk)
        api.ajax('/api/v3/desktop/jumperurl/' + pk,'GET',{}).done(function(data) {
            if(data.jumperurl != false){
                $('#jumperurl').show();
                $('.btn-copy-jumperurl').show();
                //NOTE: With this it will fire ifChecked event, and generate new key
                // and we don't want it now as we are just setting de initial state
                // and don't want to reset de key again if already exists!
                //$('#jumperurl-check').iCheck('check');
                $('#jumperurl-check').prop('checked',true).iCheck('update');

                $('#jumperurl').val(location.protocol + '//' + location.host+'/vw/'+data.jumperurl);
            }else{
                $('#jumperurl-check').iCheck('update')[0].unchecked;
                $('#jumperurl').hide();
                $('.btn-copy-jumperurl').hide();
            }
        });
    });

    $('#jumperurl-check').unbind('ifChecked').on('ifChecked', function(event){
        if($('#jumperurl').val()==''){
            pk=$('#modalJumperurlForm #id').val();
            $.ajax({
                url: '/api/v3/desktop/jumperurl_reset/' + pk,
                type: 'PUT',
                contentType: "application/json",
                data: JSON.stringify({"disabled" : false}),
                success: function(data) {
                    $('#jumperurl').val(location.protocol + '//' + location.host+'/vw/'+data);
                }
            })
            $('#jumperurl').show();
            $('.btn-copy-jumperurl').show();
        }
        });
    $('#jumperurl-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
        pk=$('#modalJumperurlForm #id').val();
        new PNotify({
            title: 'Confirmation Needed',
                text: "Are you sure you want to delete direct viewer access url?",
                hide: false,
                opacity: 0.9,
                confirm: {
                    confirm: true
                },
                buttons: {
                    closer: false,
                    sticker: false
                },
                history: {
                    history: false
                },
                addclass: 'pnotify-center'
            }).get().on('pnotify.confirm', function() {
                pk=$('#modalJumperurlForm #id').val();
                $.ajax({
                    url: '/api/v3/desktop/jumperurl_reset/' + pk,
                    type: 'PUT',
                    contentType: "application/json",
                    data: JSON.stringify({"disabled" : true}),
                    success: function(data) {
                        $('#jumperurl').val('');
                    }
                })
                $('#jumperurl').hide();
                $('.btn-copy-jumperurl').hide();
            }).on('pnotify.cancel', function() {
                $('#jumperurl-check').iCheck('check');
                $('#jumperurl').show();
                $('.btn-copy-jumperurl').show();
            });
        });

    $('.btn-copy-jumperurl').on('click', function () {
        $('#jumperurl').prop('disabled',false).select().prop('disabled',true);
        document.execCommand("copy");
    });

    $('.btn-forcedhyp').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        $("#modalForcedhypForm")[0].reset();
        $('#modalForcedhypForm #id').val(pk);
        $('#modalForcedhyp').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $.ajax({
            type: "POST",
            url:"/api/v3/admin/table/domains",
            data: JSON.stringify({'id':pk,'pluck':['id','forced_hyp']}),
            contentType: 'application/json',
            accept: "application/json",
            success: function(data)
            {
                if('forced_hyp' in data && data.forced_hyp != false && data.forced_hyp != []){
                    HypervisorsDropdown(data.forced_hyp[0]);
                    $('#modalForcedhypForm #forced_hyp').show();
                    //NOTE: With this it will fire ifChecked event, and generate new key
                    // and we don't want it now as we are just setting de initial state
                    // and don't want to reset de key again if already exists!
                    //$('#jumperurl-check').iCheck('check');
                    $('#forcedhyp-check').prop('checked',true).iCheck('update');
                }else{
                    $('#forcedhyp-check').iCheck('update')[0].unchecked;
                    $('#modalForcedhypForm #forced_hyp').hide();
                }
            },
            error: function(data)
            {
                new PNotify({
                    title: "ERROR",
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 15000,
                    opacity: 1
                });
            }
        });
    });

    $('#forcedhyp-check').unbind('ifChecked').on('ifChecked', function(event){
        if($('#forced_hyp').val()==''){
            pk=$('#modalForcedhypForm #id').val();
            $.ajax({
                type: "POST",
                url:"/api/v3/admin/table/domains",
                data: JSON.stringify({'id':pk,'pluck':['id','forced_hyp']}),
                contentType: 'application/json',
                accept: "application/json",
                success: function(data)
                {
                    if('forced_hyp' in data && data.forced_hyp != false && data.forced_hyp != []){
                        HypervisorsDropdown(data.forced_hyp[0]);
                    }else{
                        HypervisorsDropdown('');
                    }
                },
                error: function(data)
                {
                    new PNotify({
                        title: "ERROR",
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 15000,
                        opacity: 1
                    });
                }
            });
            $('#modalForcedhypForm #forced_hyp').show();
        }
        });
    $('#forcedhyp-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
        pk=$('#modalForcedhypForm #id').val();

        $('#modalForcedhypForm #forced_hyp').hide();
        $("#modalForcedhypForm #forced_hyp").empty();
    });

    $("#modalForcedhyp #send").off('click').on('click', function(e){
        var notice = new PNotify({
            text: 'Updating selected item...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        data=$('#modalForcedhypForm').serializeObject();
        $.ajax({
            type: 'PUT',
            url: `/api/v3/domain/${data["id"]}`,
            data: JSON.stringify({
                ...( ! ("forced_hyp"  in data) && {"forced_hyp": false} ),
                ...( "forced_hyp" in data && {"forced_hyp": [data.forced_hyp]} ),
            }),
            contentType: 'application/json',
            error: function(data) {
                notice.update({
                    title: 'ERROR updating forced hypervisor',
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            },
            success: function(data) {
                $('form').each(function() { this.reset() });
                $('.modal').modal('hide');
                notice.update({
                    title: 'Updated',
                    text: 'Forced hypervisor updated successfully',
                    hide: true,
                    delay: 2000,
                    icon: 'fa fa-' + data.icon,
                    opacity: 1,
                    type: 'success'
                })
            }
        })
    });

    $('.btn-favouritehyp').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        $("#modalFavouriteHypForm")[0].reset();
        $('#modalFavouriteHypForm #id').val(pk);
        $('#modalFavouriteHyp').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $.ajax({
            type: "POST",
            url:"/api/v3/admin/table/domains",
            data: JSON.stringify({'id':pk,'pluck':['id','favourite_hyp']}),
            contentType: 'application/json',
            accept: "application/json",
            success: function(data)
            {
                if('favourite_hyp' in data && data.favourite_hyp != false && data.favourite_hyp != []){
                    HypervisorsFavDropdown(data.favourite_hyp[0]);
                    $('#modalFavouriteHypForm #favourite_hyp').show();
                    //NOTE: With this it will fire ifChecked event, and generate new key
                    // and we don't want it now as we are just setting de initial state
                    // and don't want to reset de key again if already exists!
                    //$('#jumperurl-check').iCheck('check');
                    $('#favouritehyp-check').prop('checked',true).iCheck('update');
                }else{
                    $('#favouritehyp-check').iCheck('update')[0].unchecked;
                    $('#modalFavouriteHypForm #favourite_hyp').hide();
                }
            },
            error: function(data)
            {
                new PNotify({
                    title: "ERROR",
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 15000,
                    opacity: 1
                });
            }
        });
    });

    $('#favouritehyp-check').unbind('ifChecked').on('ifChecked', function(event){
        if($('#favourite_hyp').val() == ''){
            pk=$('#modalFavouriteHypForm #id').val();
            $.ajax({
                type: "POST",
                url:"/api/v3/admin/table/domains",
                data: JSON.stringify({'id':pk,'pluck':['id','favourite_hyp']}),
                contentType: 'application/json',
                accept: "application/json",
                success: function(data)
                {
                    if('favourite_hyp' in data && data.favourite_hyp != false && data.favourite_hyp != []){
                        HypervisorsFavDropdown(data.favourite_hyp[0]);
                    }else{
                        HypervisorsFavDropdown('');
                    }
                }
            });
            $('#modalFavouriteHypForm #favourite_hyp').show();
        }
        });

    $('#favouritehyp-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
        pk=$('#modalFavouriteHypForm #id').val();
        $('#modalFavouriteHypForm #favourite_hyp').hide();
        $("#modalFavouriteHypForm #favourite_hyp").empty();
    });

    $("#modalFavouriteHyp #send").off('click').on('click', function(e){
        var notice = new PNotify({
            text: 'Updating selected item...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        data=$('#modalFavouriteHypForm').serializeObject();
        $.ajax({
            type: 'PUT',
            url: `/api/v3/domain/${data["id"]}`,
            data: JSON.stringify({
                ...( ! ("favourite_hyp"  in data) && {"favourite_hyp": false} ),
                ...( "favourite_hyp" in data && {"favourite_hyp": [data.favourite_hyp]} ),
            }),
            contentType: 'application/json',
            error: function(data) {
                notice.update({
                    title: 'ERROR updating favourite hypervisor',
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            },
            success: function(data) {
                $('form').each(function() { this.reset() });
                $('.modal').modal('hide');
                notice.update({
                    title: 'Updated',
                    text: 'Favourite hypervisor updated successfully',
                    hide: true,
                    delay: 2000,
                    icon: 'fa fa-' + data.icon,
                    opacity: 1,
                    type: 'success'
                })
            }
        })
    });
}

function HypervisorsDropdown(selected) {
    $("#modalForcedhypForm #forced_hyp").empty();
    $.ajax({
        type: "POST",
        url:"/api/v3/admin/table/hypervisors",
        data: JSON.stringify({
            'pluck': ['id','hostname']
        }),
        contentType: 'application/json',
        accept: "application/json",
        success: function(data)
        {
            data.forEach(function(hypervisor){
                $("#modalForcedhypForm #forced_hyp").append('<option value=' + hypervisor.id + '>' + hypervisor.id+' ('+hypervisor.hostname+')' + '</option>');
                if(hypervisor.id == selected){
                    $('#modalForcedhypForm #forced_hyp option[value="'+hypervisor.id+'"]').prop("selected",true);
                }
            });
        }
    });
}

function HypervisorsFavDropdown(selected) {
    $("#modalFavouriteHypForm #favourite_hyp").empty();
    $.ajax({
        type: "POST",
        url:"/api/v3/admin/table/hypervisors",
        data: JSON.stringify({
            'pluck': ['id','hostname']
        }),
        contentType: 'application/json',
        accept: "application/json",
        success: function(data)
        {
            data.forEach(function(hypervisor){
                $("#modalFavouriteHypForm #favourite_hyp").append('<option value=' + hypervisor.id + '>' + hypervisor.id+' ('+hypervisor.hostname+')' + '</option>');
                if(hypervisor.id == selected){
                    $('#modalFavouriteHypForm #favourite_hyp option[value="'+hypervisor.id+'"]').prop("selected",true);
                }
            });
        }
    });
}

function setDefaultsTemplate(id) {
    $.ajax({
        type: "GET",
        url:"/api/v3/domain/info/" + id,
        success: function(data)
        {
            $('.template-id').val(id);
            $('.template-id').attr('data-pk', id);
            $('.template-name').val('Template '+data.name);
            $('.template-description').val(data.description);
        }
    });
}

function populate_tree_template_delete(id) {
    $.ajax({
        type: "GET",
        url:"/api/v3/admin/desktops/tree_list/" + id,
        contentType: 'application/json',
        success: function(data)
        {
            const rootElement = $('#nestedTemplateTable tbody');
            $('#nestedTemplateTable tbody').html('')
            renderTable(data, rootElement,1, renderTemplateTree);
        }
    });
}

//~ RENDER DATATABLE
function addDomainDetailPannel ( d ) {
        $newPanel = $template_domain.clone();
        if(kind=='desktop'){
            $newPanel = $template_domain.clone();
            $newPanel.find('#derivates-d\\.id').remove();
        }else{
            $newPanel = $admin_template_domain.clone();
        }
        $newPanel.html(function(i, oldHtml){
            return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name);
        });
        return $newPanel
}

function setDomainDetailButtonsStatus(id,status,server){
    if(status=='Started' || status=='Starting' || status == 'Shutting-down'){
        $('#actions-'+id+' *[class^="btn"]').prop('disabled', true);
        $('#actions-'+id+' .btn-jumperurl').prop('disabled', false);
    }else{
        $('#actions-'+id+' *[class^="btn"]').prop('disabled', false);
    }
    $('#actions-'+id+' .btn-server').prop('disabled', false);
    if (server) {
        $('#actions-'+id+' .btn-template').prop('disabled', true);
    }
}

function icon(data){
       viewer=""
       viewerIP="'No client viewer'"
       if(data['viewer-client_since']){viewer=" style='color:green' ";viewerIP="'Viewer client from IP: "+data['viewer-client_addr']+"'";}
       if(data.icon=='windows' || data.icon=='linux'){
           return "<i class='fa fa-"+data.icon+" fa-2x ' "+viewer+" title="+viewerIP+"></i>";
        }else{
            return "<span class='fl-"+data.icon+" fa-2x' "+viewer+" title="+viewerIP+"></span>";
        }
}

function renderDisplay(data){
        if(['Started', 'Shutting-down', 'Stopping'].includes(data.status)){
            return '<button type="button" id="btn-display" class="btn btn-pill-right btn-success btn-xs"> \
                    <i class="fa fa-desktop"></i> Show</button>';
        }
        return ''
}

    $("#modalEditDesktop #send").on('click', function(e){
            var form = $('#modalEdit');
            form.parsley().validate();
            if (form.parsley().isValid()){
                data=$('#modalEdit').serializeObject();
                data['reservables-vgpus'] = [data['reservables-vgpus']]
                data=parse_desktop(JSON.unflatten(parseViewersOptions(data)));
                var notice = new PNotify({
                    text: 'Updating selected item...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: 'PUT',
                    url: '/api/v3/domain/'+data["id"],
                    data: JSON.stringify(data),
                    contentType: 'application/json',
                    error: function(data) {
                        notice.update({
                            title: 'ERROR updating desktop',
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        })
                    },
                    success: function(data) {
                        $("#modalEdit")[0].reset();
                        $("#modalEditDesktop").modal('hide');
                        domains_table.ajax.reload()
                        notice.update({
                            title: 'Updated',
                            text: 'Domain updated successfully',
                            hide: true,
                            delay: 2000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                    }
                })
            }
        });

    $("#modalEditXml #send").on('click', function(e){
        var notice = new PNotify({
            text: 'Updating xml for selected item(s)...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        var form = $('#modalEditXmlForm');
        id=$('#modalEditXmlForm #id').val();
        xml=$('#modalEditXmlForm #xml').val();
        $.ajax({
            type: 'PUT',
            url: '/api/v3/domain/'+id,
            data: JSON.stringify({'xml':xml}),
            contentType: 'application/json',
            error: function(data) {
                notice.update({
                    title: 'ERROR updating XML',
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            },
            success: function(data) {
                $("#modalEditXmlForm")[0].reset();
                $("#modalEditXml").modal('hide');
                notice.update({
                    title: 'Updated',
                    text: 'Domain XML updated successfully',
                    hide: true,
                    delay: 2000,
                    icon: 'fa fa-' + data.icon,
                    opacity: 1,
                    type: 'success'
                })
            }
        })
    });

        function parse_desktop(data){
            return {
                "id": data["id"],
                "name": data["name"],
                "description": data["description"],
                "guest_properties": data["guest_properties"],
                "hardware": {
                    ...("virtualization_nested" in data["hardware"]) && {"virtualization_nested": true},
                    ...(! ("virtualization_nested" in data["hardware"]) && {"virtualization_nested": false}),
                    ...("vcpus" in data["hardware"]) && {"vcpus": parseInt(data["hardware"]["vcpus"])},
                    ...("memory" in data["hardware"]) && {"memory": parseFloat(data["hardware"]["memory"])},
                    ...("videos" in data["hardware"]) && {"videos": [data["hardware"]["videos"]]},
                    ...("boot_order" in data["hardware"]) && {"boot_order": [data["hardware"]["boot_order"]]},
                    ...("interfaces" in data["hardware"]) && {"interfaces": data["hardware"]["interfaces"]},
                    ...("disk_bus" in data["hardware"]) && {"disk_bus": data["hardware"]["disk_bus"]},
                    ...("disk_size" in data["hardware"]) && {"disk_size": parseInt(data["hardware"]["disk_size"])},
                    ...( true) && {"isos":[]},
                    ...("m" in data && "isos" in data["m"]) && {"isos": setMediaIds(data["m"]["isos"])},
                    ...( true) && {"floppies":[]},
                    ...("m" in data && "floppies" in data["m"]) && {"floppies": setMediaIds(data["m"]["floppies"])},
                    "reservables": {
                        ...( true ) && {"vgpus":data["reservables"]["vgpus"]},
                        ...( data["reservables"]["vgpus"].includes(undefined) || data["reservables"]["vgpus"] == null || data["reservables"]["vgpus"].includes("None") ) &&  {"vgpus": null},
                    },
                  },
                }
        }

        function populate_users(){
            if($("#user_id").data('select2')){
                $("#user_id").select2('destroy');
            }
            $("#user_id").select2({
                placeholder:"Type at least 2 letters to search.",
                minimumInputLength: 2,
                maximumSelectionLength: 1,
                multiple: true,
                dropdownparent: $("#modalDuplicateTemplateForm"),
                ajax: {
                    type: "POST",
                    url: '/admin/allowed/term/users',
                    dataType: 'json',
                    contentType: "application/json",
                    delay: 250,
                    data: function (params) {
                        return  JSON.stringify({
                            term: params.term,
                            pluck: ['id','name']
                        });
                    },
                    processResults: function (data) {
                        return {
                            results: $.map(data, function (item, i) {
                                return {
                                    text: item.name + '['+item['uid']+'] ',
                                    id: item.id
                                }
                            })
                        };
                    }
                },
            });
        };
