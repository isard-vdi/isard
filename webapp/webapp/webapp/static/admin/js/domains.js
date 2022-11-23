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

// column to sort by 'last accessed' in desktops table
order=13

columns= [
				{
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
                { "data": "icon" },
                { "data": "server", "width": "10px", "defaultContent":"-"},
                { "data": "hyp_started", "width": "100px"},
				{ "data": "name"},
				{ "data": "description"},
				{ "data": "ram"},
				{ "data": "create_dict.hardware.vcpus"},
				{ "data": null},
				{ "data": "status"},
				{ "data": "username"},
				{ "data": "category"},
				{ "data": "group"},
                { "data": "accessed",
                 'defaultContent': ''},
                {
                    "className": 'text-center',
                    "data": null,
                    "orderable": false,
                    "defaultContent": '<input type="checkbox" class="form-check-input"></input>'
                }
                ]

columnDefs = [
    {
        "targets": 1,
        "render": function ( data, type, full, meta ) {
            img_url = location.protocol+'//' + document.domain + ':' + location.port + full.image.url
            return "<img src='"+img_url+"' width='50px'>"
        }
    },{
        "targets": 2,
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
        "targets": 3,
        "render": function (data, type, full, meta) {
            return renderHypStarted(full)
        }
    },{
        "targets": 6,
        "width": "100px",
        "render": function (data, type, full, meta) {
            return (full.create_dict.hardware.memory / 1024 / 1024).toFixed(2) + "GB"
        }
    },{
        "targets": 8,
        "width": "100px",
        "render": function (data, type, full, meta) {
            return renderAction(full) + renderDisplay(full)
        }
    },{
        "targets": 9,
        "render": function (data, type, full, meta) {
            return renderStatus(full)
        }
    },{
        "targets": 13,
        "render": function (data, type, full, meta) {
            if ( type === 'display' || type === 'filter' ) {
                return moment.unix(full.accessed).fromNow()
            }
            return full.accessed
        }
    }
]

// Templates table render
if(url!="Desktops"){
    // Remove the desktops last column (used for bulk actions)
    columns.splice(14, 1)
    // Remove the server and hypervisor column
    columns.splice(2,2)
    // Remove the ram, vcpu, viewer and status columns
    columns.splice(4, 4)
    // Add the enabled, derivates and allowed columns
    columns.splice(
        7,
        0,
        {
            "data": 'enabled',
            "className": 'text-center',
            "orderable": false,
            "defaultContent": '<input type="checkbox" class="form-check-input" checked></input>'
        },
        {"data": "derivates"},
        {"defaultContent": '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button>'},
    );
    // Remove the custom rendering of the ram, viewer and status
    columnDefs.splice(1, 5)
    // Change the last access column custom render target
    columnDefs[1]["targets"]=10
    // Add the enabled column render
    columnDefs.push({
        "targets": 7,
        "render": function ( data, type, full, meta ) {
            if( full.enabled ){
                return '<input id="chk-enabled" type="checkbox" class="form-check-input" checked></input><span style="display: none;">' + data + '</span>'
            }else{
                return '<input id="chk-enabled" type="checkbox" class="form-check-input"></input><span style="display: none;">' +data + '</span>'
            }
        }
    })
    // sort by 'last accessed' in templates table
    order = 10;

    $.fn.dataTable.ext.search.push(function (settings, searchData, index, rowData, counter ) {
            search_val = $('.panel_toolbox .btn-disabled').attr('view')
            if (search_val == 'false') {
                return true;
            }
            else if (
               searchData[7] == search_val
            ) {
                return true;
            }
            return false;
    });
    
}

$(document).ready(function() {
    $('.admin-status').show()
    $template_domain = $(".template-detail-domain");
    $admin_template_domain = $(".admin-template-detail-domain");

    var stopping_timer=null
    modal_add_desktops = $('#modal_add_desktops').DataTable()
    initalize_modal_all_desktops_events()
    $('.btn-add-desktop').on('click', function () {
        $('#allowed-title').html('')
        $('#alloweds_panel').css('display','block');
        setAlloweds_add('#alloweds-block');
        if ($('meta[id=user_data]').attr('data-role') == 'manager'){
            $('#categories_pannel').hide();
            $('#roles_pannel').hide();
        }

        $("#modalAddDesktop #send-block").unbind('click');
        $("#modalAddDesktop #send-block").on('click', function(e){
            var form = $('#modalAdd');

            form.parsley().validate();
    
            if (form.parsley().isValid()){
                template_id=$('#modalAddDesktop #template').val();
                if (template_id !=''){
                    data=$('#modalAdd').serializeObject();
                    data=replaceAlloweds_arrays('#modalAddDesktop #alloweds-block',data)
                    name = data["name"]
                    description = data["description"]
                    allowed = data["allowed"]
                    
                    var notice = new PNotify({
                        text: 'Creating desktops...',
                        hide: true,
                        opacity: 1,
                        icon: 'fa fa-spinner fa-pulse'
                    })
                    
                    $('form').each(function() {
                        this.reset()
                    })
                    $('.modal').modal('hide')
    
                    $.ajax({
                        type: "POST",
                        url:"/api/v3/persistent_desktop/bulk",
                        data: JSON.stringify({name, template_id, description, allowed}),
                        contentType: "application/json",
                        error: function(data) {
                            notice.update({
                                title: 'ERROR',
                                text: data.responseJSON.description,
                                type: 'error',
                                hide: true,
                                icon: 'fa fa-warning',
                                delay: 5000,
                                opacity: 1
                            })
                        },
                        success: function(data) {
                            notice.update({
                                title: 'New desktops',
                                text: 'Desktops created successfully',
                                hide: true,
                                delay: 2000,
                                icon: 'fa fa-' + data.icon,
                                opacity: 1,
                                type: 'success'
                            })
                        }
                    });
                }else{
                    $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                }
            }
        });

         if($('.limits-desktops-bar').attr('aria-valuenow') >=100){
            new PNotify({
                title: "Quota for creating desktops full.",
                    text: "Can't create another desktop, category quota full.",
                    hide: true,
                    delay: 3000,
                    icon: 'fa fa-alert-sign',
                    opacity: 1,
                    type: 'error'
                });
        }else{	
            setHardwareOptions('#modalAddDesktop');
            $("#modalAdd")[0].reset();
            $('#modalAddDesktop').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            $('#modalAddDesktop #hardware-block').hide();
            $('#modalAdd').parsley();
            modal_add_desktop_datatables();
        }
    });

    $("#modalTemplateDesktop #send").on('click', function(e){
            var form = $('#modalTemplateDesktopForm');
            form.parsley().validate();
            if (form.parsley().isValid()){
                desktop_id=$('#modalTemplateDesktopForm #id').val();
                if (desktop_id !=''){
                    data=$('#modalTemplateDesktopForm').serializeObject();
                    data=replaceAlloweds_arrays('#modalTemplateDesktopForm #alloweds-add',data)
                    data['enabled']=$('#modalTemplateDesktopForm #enabled').prop('checked')
                    
                    name=data["name"]
                    allowed=data["allowed"]
                    description=data["description"]
                    enabled=data["enabled"]

                    var notice = new PNotify({
                        text: 'Creating desktop...',
                        hide: false,
                        opacity: 1,
                        icon: 'fa fa-spinner fa-pulse'
                    })

                    $('form').each(function() {
                        this.reset()
                    })
                    $('.modal').modal('hide');

                    $.ajax({
                        type: "POST",
                        url:"/api/v3/template",
                        data: JSON.stringify({name, desktop_id, allowed, description, enabled}),
                        contentType: "application/json",
                        error: function(data) {
                            notice.update({
                                title: 'ERROR',
                                text: 'Cannot create template ' + name,
                                type: 'error',
                                hide: true,
                                icon: 'fa fa-warning',
                                delay: 5000,
                                opacity: 1
                            })
                        },
                        success: function(data) {
                            notice.update({
                                title: 'New template',
                                text: 'Template '+ name + ' created successfully',
                                hide: true,
                                delay: 2000,
                                icon: 'fa fa-' + data.icon,
                                opacity: 1,
                                type: 'success'
                            })
                        }
                    });
                    
                }else{
                    $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                }
            }
        });
        
    $("#modalDeleteTemplate #send").on('click', function(e){

        selected = $("#modalDeleteTemplate .tree_template_delete").fancytree('getTree').getSelectedNodes();
        todelete = []
        selected.forEach(function (item) {
            todelete.push({"id":item.data.id, "title":item.title, "kind":item.data.kind, "status":item.data.status})
        });
        var notice = new PNotify({
            text: 'Deleting selected item(s)...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        $('form').each(function() {
            this.reset()
        })
        $('.modal').modal('hide')
        $.ajax({
            type: 'DELETE',
            url: '/api/v3/admin/domains',
            data: JSON.stringify(todelete),
            contentType: 'application/json',
            error: function(data) {
                notice.update({
                    title: 'ERROR',
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
                notice.update({
                    title: data.title,
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
                text: 'Creating duplicate template...',
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
                        title: 'ERROR',
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
                    notice.update({
                        title: data.title,
                        text: 'Template duplicated',
                        hide: true,
                        delay: 2000,
                        icon: 'fa fa-' + data.icon,
                        opacity: 1,
                        type: 'success'
                    })
                }
            })
        }
        $('form').each(function() {
            this.reset()
        })
        $('.modal').modal('hide')
    });

    // Setup - add a text input to each footer cell
    $('#domains tfoot th').each( function () {
        var title = $(this).text();
        if (['','Icon','Hypervisor','Action', 'Enabled'].indexOf(title) == -1){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );
            
		domains_table= $('#domains').DataTable({
			"ajax": {
				"url": "/admin/domains",
                "type": "GET",
                "dataSrc":'',
                "data": { 'kind': kind }
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
			"deferRender": true,
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

    domains_table.on( 'click', 'tr[role="row"]', function (e) { 
        if (kind =='desktop') {
            toggleRow(this, e);
        }
     });

    $('#mactions').on('change', function () {
        action=$(this).val();
        names=''
        ids=[]

        if(domains_table.rows('.active').data().length){
            $.each(domains_table.rows('.active').data(),function(key, value){
                names+=value['name']+'\n';
                ids.push(value['id']);
            });
            var text = "You are about to "+action+" these desktops:\n\n "+names
        }else{ 
            $.each(domains_table.rows({filter: 'applied'}).data(),function(key, value){
                ids.push(value['id']);
            });
            var text = "You are about to "+action+" "+domains_table.rows({filter: 'applied'}).data().length+" desktops!\n All the desktops in list!"
        }
				new PNotify({
						title: 'Warning!',
							text: text,
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
                api.ajax('/api/v3/admin/multiple_actions', 'POST', {'ids':ids, 'action':action}).done(function(data) {
                    notify(data)
                }).fail(function(jqXHR) {
                    notify(jqXHR.responseJSON)
                }).always(function() {
                    $('#mactions option[value="none"]').prop("selected", true);
                    $('#domains tr.active').removeClass('active')
                })
                    }).on('pnotify.cancel', function() {
                        $('#mactions option[value="none"]').prop("selected",true);
				});
    } );

    $('#domains').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = domains_table.row( tr );
 
        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            // Close other rows
             if ( domains_table.row( '.shown' ).length ) {
                      $('.details-control', domains_table.row( '.shown' ).node()).click();
              }
             if (row.data().status=='Creating'){
                 //In this case better not to open detail as ajax snippets will fail
                 //Maybe needs to be blocked also on other -ing's
						new PNotify({
						title: "Domain is being created",
							text: "Wait till domain ["+row.data().name+"] creation completes to view details",
							hide: true,
							delay: 3000,
							icon: 'fa fa-alert-sign',
							opacity: 1,
							type: 'error'
						});
             }else{
                // Open this row
                row.child( addDomainDetailPannel(row.data()) ).show();
                tr.addClass('shown');
                $('#status-detail-'+row.data().id).html(row.data().detail);
                actionsDomainDetail();
                setDomainDetailButtonsStatus(row.data().id,row.data().status,row.data().server)
                setDomainHotplug(row.data().id, row.data());
                setHardwareDomainDefaults_viewer('#hardware-'+row.data().id,row.data());
                if(kind!="desktop"){
                    setAlloweds_viewer('#alloweds-'+row.data().id,row.data().id);
                }
            }
        }
    } );

    $('#domains').find(' tbody').on( 'click', 'input', function () {
        var pk=domains_table.row( $(this).parents('tr') ).id();
        switch($(this).attr('id')){
            case 'chk-enabled':
                if ($(this).is(":checked")){
                    enabled=true
                }else{
                    enabled=false
                }
                api.ajax('/api/v3/template/update',
                        'PUT',
                        {'id':pk,
                        'enabled':enabled})
                .fail(function(jqXHR) {
                    new PNotify({
                        title: "Template enable/disable",
                            text: "Could not update!",
                            hide: true,
                            delay: 3000,
                            icon: 'fa fa-alert-sign',
                            opacity: 1,
                            type: 'error'
                        });
                        domains_table.ajax.reload()
                }); 
            break;
        }
    })

	// DataTable buttons
    $('#domains tbody').on( 'click', 'button', function () {
        var data = domains_table.row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
            case 'btn-play':
				if($('.quota-play .perc').text() >=100){
					new PNotify({
						title: "Quota for running desktops full.",
							text: "Can't start another desktop, quota full.",
							hide: true,
							delay: 3000,
							icon: 'fa fa-alert-sign',
							opacity: 1,
							type: 'error'
						});
				}else{
                    $.ajax({
                        type: "GET",
                        url: '/api/v3/desktop/start/' + data["id"],
                        data: {'pk':data['id'],'name':'status','value':'Starting'},
                        contentType: "application/json",
                        cache: false,
                        error: function(data) {
                            new PNotify({
                                title: 'ERROR',
                                text: data.responseJSON.description,
                                type: 'error',
                                hide: true,
                                icon: 'fa fa-warning',
                                delay: 5000,
                                opacity: 1
                            })
                        },
                    })
				}          
                break;
            case 'btn-stop':
                // When desktop is 'Shutting-down' and click on 'Force stop' button
                if(data['status']=='Shutting-down'){
                    api.ajax('/api/v3/desktop/stop/' + data["id"], 'GET',{'pk':data['id'],'name':'status','value':'Stopping'}).done(function(data) {});
                }else{
                    api.ajax('/api/v3/desktop/stop/' + data["id"], 'GET',{'pk':data['id'],'name':'status','value':'Shutting-down'}).done(function(data) {});
                }
                break;
            case 'btn-display':
				new PNotify({
						title: 'Connect to user viewer!',
							text: "By connecting to desktop "+ name+" you will disconnect and gain access to that user current desktop.\n\n \
								   Please, think twice before doing this as it could be illegal depending on your relation with the user. \n\n ",
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
                            setViewerButtons(data,socket);

                            if('viewer' in data && 'guest_ip' in data['viewer']){
                                viewerButtonsIP(data.id,data['viewer']['guest_ip'])
                            }
                            $('#modalOpenViewer').modal({
                                backdrop: 'static',
                                keyboard: false
                            }).modal('show');
						}).on('pnotify.cancel', function() {
				});
                break;
            case 'btn-alloweds':
                modalAllowedsFormShow('domains',data)
                break;
        }
    });

    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/administrators', {
        'query': {'jwt': localStorage.getItem("token")},
        'path': '/api/v3/socket.io/',
        'transports': ['websocket']
    });

    socket.on('connect', function() {
        connection_done();
        console.log('Listening admins namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });

    startClientVpnSocket(socket)
    socket.on('user_quota', function(data) {
        console.log('Quota update')
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

    socket.on(kind+'_data', function(data){
        var data = JSON.parse(data);
        if(data.status =='Started' && 'viewer' in data && 'guest_ip' in data['viewer']){
            if(!('viewer' in domains_table.row('#'+data.id).data()) || !('guest_ip' in domains_table.row('#'+data.id).data())){
                //console.log('NEW IP ARRIVED!: '+data['viewer']['guest_ip'])
                viewerButtonsIP(data.id,data['viewer']['guest_ip'])
            }
        }        
        dtUpdateInsert(domains_table,data,false);
        setDomainDetailButtonsStatus(data.id, data.status, data.server);
    });

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
    
});

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

    if(kind=="desktop"){
        $('.btn-delete-template').remove()

	$('.btn-template').on('click', function () {
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
            
			$('#modalTemplateDesktop').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');

            setAlloweds_add('#modalTemplateDesktop #alloweds-add');
        }
	});

    $('.btn-delete').on('click', function () {
                    var pk=$(this).closest("[data-pk]").attr("data-pk");
                    var name=$(this).closest("[data-pk]").attr("data-name");
                    new PNotify({
                            title: 'Confirmation Needed',
                                text: "Are you sure you want to delete virtual machine: "+name+"?",
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
                                api.ajax('/api/v3/desktop/' + pk, 'DELETE').done(function() {});
                            }).on('pnotify.cancel', function() {
                    });	
        });
    }else{
        $('.btn-delete').remove()
        $('.btn-template').remove()

		$('.btn-delete-template').on('click', function () {	
            var pk = $(this).closest("[data-pk]").attr("data-pk")
            $('#modalDeleteTemplate').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
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
    }


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
        api.ajax('/api/v3/admin/table/domains','POST',{'id':pk,'pluck':['id','forced_hyp']}).done(function(data) { 
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
        }); 
    });

    $('#forcedhyp-check').unbind('ifChecked').on('ifChecked', function(event){
        if($('#forced_hyp').val()==''){
            pk=$('#modalForcedhypForm #id').val();  
            api.ajax('/api/v3/admin/table/domains','POST',{'id':pk,'pluck':['id','forced_hyp']}).done(function(data) {        
                
                if('forced_hyp' in data && data.forced_hyp != false && data.forced_hyp != []){
                    HypervisorsDropdown(data.forced_hyp[0]);
                }else{
                    HypervisorsDropdown('');
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
            url: '/api/v3/domain/'+data["id"],
            data: JSON.stringify({
                ...( ! ("forced_hyp"  in data) && {"forced_hyp": false} ),
                ...( "forced_hyp" in data && {"forced_hyp": [data.forced_hyp]} ),
            }),
            contentType: 'application/json',
            error: function(data) {
                notice.update({
                    title: 'ERROR',
                    text: 'Something went wrong when updating',
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
                    text: 'Item updated successfully',
                    hide: true,
                    delay: 2000,
                    icon: 'fa fa-' + data.icon,
                    opacity: 1,
                    type: 'success'
                })
            }
        })
    });

    $("#modalServer #send").off('click').on('click', function(e){
        data=$('#modalServerForm').serializeObject();
        let pk=$('#modalServerForm #id').val()
        let server=$('#modalServerForm #server').prop('checked')
        $.ajax({
            type: "PUT",
            url: "/api/v3/domain/" + pk,
            data: JSON.stringify({
                'id': pk,
                'server': server
            }),
            contentType: "application/json",
            success: function(data)
            {
                $('form').each(function() { this.reset() });
                $('.modal').modal('hide');
                new PNotify({
                    title: "Updated desktop as server",
                    text: "Server desktop has been updated...",
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-success',
                    opacity: 1,
                    type: "success"
                });
            },
            error: function(data){
                new PNotify({
                    title: "ERROR",
                    text: "Can't update desktop as server",
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 15000,
                    opacity: 1
                });
            }
        });
        $("#modalServer").modal('hide');
    });

}

function HypervisorsDropdown(selected) {
    $("#modalForcedhypForm #forced_hyp").empty();
    api.ajax('/api/v3/admin/table/hypervisors','POST',{'pluck':['id','hostname']}).done(function(data) {
        data.forEach(function(hypervisor){
            $("#modalForcedhypForm #forced_hyp").append('<option value=' + hypervisor.id + '>' + hypervisor.id+' ('+hypervisor.hostname+')' + '</option>');
            if(hypervisor.id == selected){
                $('#modalForcedhypForm #forced_hyp option[value="'+hypervisor.id+'"]').prop("selected",true);
            }
        });
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
    if(status=='Started' || status=='Starting'){
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

function renderStatus(data){
    return data.status;
    //To return the guest ip
    if('viewer' in data && 'guest_ip' in data['viewer']){
        return data['viewer']['guest_ip']
    }else{
        return 'No ip'
    }
}

function renderHypStarted(data){
    res=''
    if('forced_hyp' in data && data.forced_hyp != false && data.forced_hyp != []){
        res='<b>F: </b>'+data.forced_hyp[0]
    }
    if('hyp_started' in data && data.hyp_started != ''){ res=res+'<br><b>S: </b>'+ data.hyp_started;}
    return res
}

function renderAction(data){
    status=data.status;
    if(status=='Stopped' || status=='Failed'){
        return '<button type="button" id="btn-play" class="btn btn-pill-right btn-success btn-xs"><i class="fa fa-play"></i> Start</button>';
    }
    if(status=='Started'){
        return '<button type="button" id="btn-stop" class="btn btn-pill-left btn-danger btn-xs"><i class="fa fa-stop"></i> Stop</button>';
    }
    if(status=='Shutting-down'){
        return '<button type="button" id="btn-stop" class="btn btn-pill-left btn-danger btn-xs"><i class="fa fa-spinner fa-pulse fa-fw"></i> Force stop</button>';
    } 
    if(status=='Crashed'){
        return '<div class="Change"> <i class="fa fa-thumbs-o-down fa-2x"></i> </div>';
    } 
    if(status=='Disabled'){
            return '<i class="fa fa-times fa-2x"></i>';
    }
    return '<i class="fa fa-spinner fa-pulse fa-2x fa-fw"></i>';
}

function populate_tree_template_delete(id){
    $(":ui-fancytree").fancytree("destroy")
    $("#modalDeleteTemplate .tree_template_delete").fancytree({
        extensions: ["table"],
        table: {
          indentation: 20,      // indent 20px per node level
          nodeColumnIdx: 2,     // render the node title into the 2nd column
          checkboxColumnIdx: 0  // render the checkboxes into the 1st column
        },  
        source: {url: "/api/v3/admin/desktops/tree_list/" + id,
                cache: false},
        lazyLoad: function(event, data){
            data.result = $.ajax({
                url: "/api/v3/admin/desktops/tree_list/" + id,
                dataType: "json"
            });
            },
        checkbox: true,
        selectMode: 3,
        renderColumns: function(event, data) {
            var node = data.node,
              $tdList = $(node.tr).find(">td");
              
            // (index #0 is rendered by fancytree by adding the checkbox)
            $tdList.eq(1).text(node.getIndexHier());
            // (index #2 is rendered by fancytree)
            if(node.unselectable){
                $tdList.eq(3).html('<i class="fa fa-exclamation-triangle"></i> '+node.data.user);
                 
            }else{
                $tdList.eq(3).text(node.data.user);
            }           
            if(node.data.kind != "desktop"){
                $tdList.eq(4).html('<p style="color:black">'+node.data.kind+'</p>');
                $tdList.eq(5).html('<p style="color:black">'+node.data.category+'</p>');
                $tdList.eq(6).html('<p style="color:black">'+node.data.group+'</p>');
            }else{
                $tdList.eq(4).text(node.data.kind);
                $tdList.eq(5).text(node.data.category);
                $tdList.eq(6).text(node.data.group);
            }
            // Rendered by row template:
    //        $tdList.eq(4).html("<input type='checkbox' name='like' value='" + node.key + "'>");
          }
    });
}

    $("#modalEditDesktop #send").on('click', function(e){
            var form = $('#modalEdit');
            form.parsley().validate();
            if (form.parsley().isValid()){
                data=$('#modalEdit').serializeObject();
                if( ("viewers-file_rdpgw" in data || "viewers-file_rdpvpn" in data || "viewers-browser_rdp" in data) && ! data["hardware-interfaces"].includes("wireguard") ){
                    new PNotify({
                        title: "Incompatible options",
                            text: "RDP viewers need the wireguard network. Please add wireguard network to this desktop or remove RDP viewers.",
                            hide: true,
                            delay: 6000,
                            icon: 'fa fa-alert-sign',
                            opacity: 1,
                            type: 'error'
                        });
                    return
                }
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
                            title: 'ERROR',
                            text: 'Something went wrong when updating',
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
                            text: 'Item updated successfully',
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
                    title: 'ERROR',
                    text: 'Something went wrong when updating xml',
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
                    title: data.title,
                    text: 'Item xml updated successfully',
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
                    url: '/admin/alloweds/term/users',
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

