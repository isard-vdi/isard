/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

socket=null
user={}
$(document).ready(function() {
    $('.admin-status').hide()
    user['role']=$('#user-data').data("role");
    $('.btn-delete-template').remove()
    modal_add_desktops = $('#modal_add_desktops').DataTable()
	initalize_modal_all_desktops_events()
    
    setViewerHelp();
 
	$template = $(".template-detail-domain");


    
	$('.btn-new').on('click', function () {
        if($('.quota-desktops .perc').text() >=100){
            new PNotify({
                title: "Quota for creating desktops full.",
                    text: "Can't create another desktop, user quota full.",
                    hide: true,
                    delay: 3000,
                    icon: 'fa fa-alert-sign',
                    opacity: 1,
                    type: 'error'
                });
        }else if($('.limits-desktops-bar').attr('aria-valuenow') >=100){
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
            //~ setHardwareDomainDefaults('#modalAddDesktop',pk);
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


	//DataTable Main renderer
	var table = $('#desktops').DataTable({
			"ajax": {
				"url": "/isard-admin/desktops/get/",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "<h1>You don't have any desktop created yet.</h1><br><h2>Create one using the +Add new button on top right of this page.</h2><br>\
                                Select your desktop from templates created and shared by the administrator."
			},           
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
				{ "data": "icon", "width": "10px" },
				{ "data": null, "width": "10px"},
				{ "data": null, "width": "10px"},
				{ "data": "status", "width": "10px"},
                { "data": null, "width": "10px"},
				{ "data": "name"},
                { "data": null, "width": "90px"},
				],
			 "order": [[3, 'desc']],		 
		"columnDefs": [ {
							"targets": 1,
							"render": function ( data, type, full, meta ) {
							  return renderIcon(full);
							}},
							{
							"targets": 2,
							"render": function ( data, type, full, meta ) {
							  return renderAction(full);
							}},
							{
							"targets": 3,
							"render": function ( data, type, full, meta ) {
							  return renderDisplay(full);
							}},
							{
							"targets": 4,
							"render": function ( data, type, full, meta ) {
							  return renderStatus(full,table);
							}},
                            {
							"targets": 5,
							"render": function ( data, type, full, meta ) {
                                if('preferred' in full['options']['viewers'] && full['options']['viewers']['preferred']){return full['options']['viewers']['preferred'].replace('-','/').toUpperCase();}
							  return '';
							}},                            
							{
							"targets": 6,
							"render": function ( data, type, full, meta ) {
							  return renderName(full);
							}},
							{
							"targets": 7,
							"render": function ( data, type, full, meta ) {
							  return renderMedia(full);
							}},
							//~ {
							//~ "targets": 7,
							//~ "render": function ( data, type, full, meta ) {
							  //~ return renderHotplugMedia(full);
							//~ }}
							]
	} );

	// DataTable detail
	$('#desktops tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = table.row( tr );
        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            row.child.remove();
            tr.removeClass('shown');
        }
        else {
            
            // Close other rows
             if ( table.row( '.shown' ).length ) {
                      $('.details-control', table.row( '.shown' ).node()).click();
              }
             //~ if (row.data().status=='Creating'){
                 //In this case better not to open detail as ajax snippets will fail
                 //Maybe needs to be blocked also on other -ing's
						//~ new PNotify({
						//~ title: "Domain is being created",
							//~ text: "Wait till domain ["+row.data().name+"] creation completes to view details",
							//~ hide: true,
							//~ delay: 3000,
							//~ icon: 'fa fa-alert-sign',
							//~ opacity: 1,
							//~ type: 'error'
						//~ });                 
             //~ }else{
                // Open this row
                row.child( addDesktopDetailPannel(row.data()) ).show();
                tr.addClass('shown');
                $('#status-detail-'+row.data().id).html(row.data().detail);
                actionsDesktopDetail();
                setDesktopDetailButtonsStatus(row.data().id,row.data().status)
                if(row.data().status=='Stopped' || row.data().status=='Started'){
                    //~ setDomainGenealogy(row.data().id);
                    setDomainHotplug(row.data().id, row.data());
                    //console.log('can edit')
                    
                    setHardwareDomainDefaults_viewer('#hardware-'+row.data().id,row.data());
                }                   
            //~ }
          }
    } );


	// DataTable buttons
    $('#desktops tbody').on( 'click', 'button', function () {
        var data = table.row( $(this).parents('tr') ).data();
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
                    socket.emit('domain_update',{'pk':data['id'],'name':'status','value':'Starting'}) 
				}          
                break;
            case 'btn-stop':
				new PNotify({
						title: 'Unplug desktop warning!',
							text: "It is NOT RECOMMENDED to continue and turn off desktop "+ name+".\n \
								   Please, properly shut down desktop from inside viewer \n\n \
								   Turn off desktop? "+ name+"?",
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
                            socket.emit('domain_update',{'pk':data['id'],'name':'status','value':'Stopping'})
						}).on('pnotify.cancel', function() {
				});	
                break;
            case 'btn-display':
                //~ chooseViewer(data,socket);
                setViewerButtons(data['id'],socket);

                $('#modalOpenViewer').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');
                        
                break;
        }
    });


    
    // SocketIO
    //~ reconnect=-1;
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/isard-admin/sio_users');
    //socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/isard-admin/sio_users', { path: '/isard-admin/socket.io' });


    
    socket.on('connect', function() {
        connection_done();
        console.log('Listening users namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
     startClientViewerSocket(socket);
     
    socket.on('user_quota', function(data) {
        var data = JSON.parse(data);
        console.log('user_quota')

        drawUserQuota(data);
    });

   
    countdown ={}
    socket.on('desktop_data', function(data){
        var data = JSON.parse(data);
        console.log('desktop_data')
        if(data.status =='Started' && table.row('#'+data.id).data().status != 'Started'){
            
            if('preferred' in data['options']['viewers'] && data['options']['viewers']['preferred']){
                socket.emit('domain_viewer',{'pk':data.id,'kind':data['options']['viewers']['preferred'],'os':getOS()});
            }else{
                 setViewerButtons(data.id,socket);
                    $('#modalOpenViewer').modal({
                        backdrop: 'static',
                        keyboard: false
                    }).modal('show');
            }
        }else{
            //~ if('ephimeral' in data && !countdown[data.id]){
                clearInterval(countdown[data.id])
                countdown[data.id]=null
            //~ }
        }
        


        dtUpdateInsert(table,data,false);
        setDesktopDetailButtonsStatus(data.id, data.status);
    });
    
    socket.on('desktop_delete', function(data){
        var data = JSON.parse(data);
        var row = table.row('#'+data.id).remove().draw();
        new PNotify({
                title: "Desktop deleted",
                text: "Desktop "+data.name+" has been deleted",
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
        });
    });
    
    socket.on('result', function (data) {
        var data = JSON.parse(data);
        if(data.title){
            new PNotify({
                    title: data.title,
                    text: data.text,
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-'+data.icon,
                    opacity: 1,
                    type: data.type
            });
        };
    });

    socket.on('add_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $("#modalAdd")[0].reset();
            $("#modalAddDesktop").modal('hide');
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

    socket.on('edit_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $("#modalEdit")[0].reset();
            $("#modalEditDesktop").modal('hide');
            //setHardwareDomainDefaults_viewer('#hardware-'+data.id,data);
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


function actionsDesktopDetail(){
	$('.btn-edit').on('click', function () {
            var pk=$(this).closest("[data-pk]").attr("data-pk");
			setHardwareOptions('#modalEditDesktop');
            setHardwareDomainDefaults('#modalEditDesktop',pk);
            $("#modalEdit")[0].reset();
			$('#modalEditDesktop').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
             $('#hardware-block').hide();
            $('#modalEdit').parsley();
            modal_edit_desktop_datatables(pk);
            
            setDomainMediaDefaults('#modalEditDesktop',pk);
            setMedia_add('#modalEditDesktop #media-block')
	});

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
			setHardwareOptions('#modalTemplateDesktop');
			setHardwareDomainDefaults('#modalTemplateDesktop',pk);
            
			$('#modalTemplateDesktop').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');

            setDomainMediaDefaults('#modalTemplateDesktop',pk);
            setMedia_add('#modalTemplateDesktop #media-block')  
            
            setAlloweds_add('#modalTemplateDesktop #alloweds-add');          
            $('#modalTemplateDesktopForm').parsley().validate();
        }
	});

        $('#modalTemplateDesktop').on('shown.bs.modal', function () {
                validator.checkAll($('#modalTemplateDesktopForm')[0]);
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
                            socket.emit('domain_update',{'pk':pk,'name':'status','value':'Deleting'})
						}).on('pnotify.cancel', function() {
				});	
	});

	$('.btn-xml').on('click', function () {
            var pk=$(this).closest("[data-pk]").attr("data-pk");
            $("#modalShowInfoForm")[0].reset();
			$('#modalEditXml').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalShowInfoForm #id').val(pk);
            $.ajax({
                type: "GET",
                url:"/isard-admin/admin/domains/xml/" + pk,
                success: function(data)
                {
                    var data = JSON.parse(data);
                    $('#xml').val(data);
                }				
            });
            //~ $('#modalEdit').parsley();
            //~ modal_edit_desktop_datatables(pk);
	});

	$('.btn-events').on('click', function () {
            var pk=$(this).closest("[data-pk]").attr("data-pk");
            $("#modalShowInfoForm")[0].reset();
			$('#modalShowInfo').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalShowInfoForm #id').val(pk);
            $.ajax({
                type: "GET",
                url:"/isard-admin/admin/domains/events/" + pk,
                success: function(data)
                {
                    var data = JSON.parse(data);
		    $('#xml').val(JSON.stringify(data, undefined, 4));
                }				
            });
            //~ $('#modalEdit').parsley();
            //~ modal_edit_desktop_datatables(pk);
	});
	
	$('.btn-messages').on('click', function () {
            var pk=$(this).closest("[data-pk]").attr("data-pk");
            $("#modalShowInfoForm")[0].reset();
			$('#modalShowInfo').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalShowInfoForm #id').val(pk);
            $.ajax({
                type: "GET",
                url:"/isard-admin/admin/domains/messages/" + pk,
                success: function(data)
                {
                    var data = JSON.parse(data);
                    $('#xml').val(JSON.stringify(data, undefined, 4));
                }				
            });
            //~ $('#modalEdit').parsley();
            //~ modal_edit_desktop_datatables(pk);
	});		
		
}
	
//~ RENDER DATATABLE	
function addDesktopDetailPannel ( d ) {
		$newPanel = $template.clone();
        $newPanel.find('#derivates-d\\.id').remove();
        $newPanel.find('.btn-xml').remove();
		$newPanel.html(function(i, oldHtml){
			return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name);
		});
		return $newPanel
}

function setDesktopDetailButtonsStatus(id,status){
    
    if(status=='Stopped'){
        $('#actions-'+id+' *[class^="btn"]').prop('disabled', false);
    }else{
        $('#actions-'+id+' *[class^="btn"]').prop('disabled', true);
    }
    if(status=='Failed'){
      $('#actions-'+id+' .btn-edit').prop('disabled', false);
      $('#actions-'+id+' .btn-delete').prop('disabled', false);
    }
}
	
function icon(name){
       if(name=='windows' || name=='linux'){
           return "<i class='fa fa-"+name+" fa-2x '></i>";
        }else{
            return "<span class='fl-"+name+" fa-2x'></span>";
		}       
}

function icon1x(name){
       if(name=='windows' || name=='linux'){
           return "<i class='fa fa-"+name+"'></i>";
        }else{
            return "<span class='fl-"+name+"'></span>";
		}       
}

function renderDisplay(data){
        if(data.status=='Stopping' || data.status =='Started'){
            return ' <div class="display"> \
					<button type="button" id="btn-display" class="btn btn-pill-right btn-success btn-xs"> \
					<i class="fa fa-desktop"></i> Show</button></div>';
        }
        return ''
}

function renderName(data){
		return '<div class="block_content" > \
      			<h2 class="title" style="height: 4px; margin-top: 0px;"> \
                <a>'+data.name+'</a> \
                </h2> \
      			<p class="excerpt" >'+data.description+'</p> \
           		</div>'
}
                        
function renderIcon(data){
		return '<span class="xe-icon" data-pk="'+data.id+'">'+icon(data.icon)+'</span>'
}

function renderIcon1x(data){
		return '<span class="xe-icon" data-pk="'+data.id+'">'+icon1x(data.icon)+'</span>'
}

function renderStatus(data,table){
        if(data.status =='Started' && 'ephimeral' in data && !countdown[data.id]){
                countdown[data.id]=setInterval(function(){
                    if(data.finish < moment().unix()){clearInterval(countdown[data.id]);}
                    data.description="<b style='color:red'>REMAINIG STARTED DESKTOP TIME: "+moment.unix(data.ephimeral.finish).diff(moment(), "seconds")+' seconds</b>'
                    dtUpdateInsert(table,data,false);
                    },1000);
        }
    
		return data.status;
}
	
function renderAction(data){
		status=data.status;
        if(status=='Stopped' || status=='Failed'){
            return '<button type="button" id="btn-play" class="btn btn-pill-right btn-success btn-xs"><i class="fa fa-play"></i> Start</button>';
        }
        if(status=='Started'){
            return '<button type="button" id="btn-stop" class="btn btn-pill-left btn-danger btn-xs"><i class="fa fa-stop"></i> Stop</button>';
        } 
        if(status=='Crashed'){
            return '<div class="Change"> <i class="fa fa-thumbs-o-down fa-2x"></i> </div>';
        } 
        if(status=='Disabled'){
                return '<i class="fa fa-times fa-2x"></i>';
        }            
        return '<i class="fa fa-spinner fa-pulse fa-2x fa-fw"></i>';
}	

//~ function renderHypStarted(data){
        //~ if('forced_hyp' in data && data.forced_hyp!=''){return '**'+data.forced_hyp+'**';}
        //~ if('hyp_started' in data){ return data.hyp_started;}
		//~ return '';
//~ }

//~ function renderEphimeral(data){ 
            
            //~ perc = data.ephimeral.minutes
            //~ time_remaining=
            //~ return data.ephimeral.minutes+''+data.accessed'<div class="progress"> \
                  //~ <div id="pbid_'+data.id+'" class="progress-bar" role="progressbar" aria-valuenow="'+perc+'" \
                  //~ aria-valuemin="0" aria-valuemax="'+data.ephimeral.minutes+'" style="width:'+perc+'%"> \
                    //~ Time remaining:'+perc+'%  \
                  //~ </div> \
                //~ </<div> '
//~ }

function renderMedia(data){
        html=''
        if('isos' in data.create_dict.hardware){
            $.each(data.create_dict.hardware.isos,function(key, value){
                html+='<i class="fa fa-circle-o fa-2x" title="ISO cd file"></i> ';
                //html+='<i class="fa fa-circle-o fa-2x" title="'+value.name+'"></i> ';
            });
        }
        if('floppies' in data.create_dict.hardware){
            $.each(data.create_dict.hardware.floppies,function(key, value){
                html+='<i class="fa fa-floppy-o fa-2x" title="Floppy disk file"></i> ';
            });
        }
        if('storage' in data.create_dict.hardware){
            $.each(data.create_dict.hardware.storage,function(key, value){
                html+='<i class="fa fa-hdd-o fa-2x" title="Storage disk file"></i> ';
            });
        }    
        return html;
}

function renderHotplugMedia(data){
        html='<button class="btn btn-xs btn-hotplug" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button> '
        if('hotplug' in data){
            $.each(data.hotplug,function(key, value){
                if(value.kind=='iso'){
                    html+='<i class="fa fa-circle-o fa-2x" title="'+value.id+'"></i> ';
                }
                if(value.kind=='fd'){
                    if(value.status=='Plugging'){
                        html+='<i class="fa fa-floppy-o fa-2x blink" title="'+value.name+'" style="color:#ff9933"></i> ';
                    }else{
                        html+='<i class="fa fa-floppy-o fa-2x" title="'+value.name+'" style="color:#0c3300"></i> ';
                    }
                }                
            });
        }
        return html;
}

function setDefaultsTemplate(id) {
	$.ajax({
		type: "GET",
		url:"/isard-admin/desktops/templateUpdate/" + id,
		success: function(data)
		{
			$('.template-id').val(id);
			$('.template-id').attr('data-pk', id);
            $('.template-name').val('Template '+data.name);
            $('.template-description').val(data.description);
		}				
	});
}




function renderTemplateKind(data){
		//~ if(data.kind=="public_template"){return "public";}
        //~ if(data.kind=="user_template"){return "private";}
	if(data.kind=='base'){return 'base';}
        return "template"
}

function modal_add_desktop_datatables(){
    modal_add_desktops.destroy()
    $('#modalAddDesktop #template').val('');
    $('#modalAddDesktop #datatables-error-status').empty()
    
    $('#modal_add_desktops thead th').each( function () {
        var title = $(this).text();
        if(title=='Name'){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
        //~ if(title=='Type'){
                    //~ column=modal_add_desktops.columns(0)
                    //~ var select = $('<select><option value=""><option value="base">Base</option><option value="public_template">Public</select>')
                        //~ .appendTo( $(column.header()).empty() )
                        //~ .on( 'change', function () {
                            //~ var val = $.fn.dataTable.util.escapeRegex(
                                //~ $(this).val()
                            //~ );
                            //~ column
                                //~ .search( val ? '^'+val+'$' : '', true, false )
                                //~ .draw();
                        //~ } );
        //~ }
    } );
    
	modal_add_desktops = $('#modal_add_desktops').DataTable({
			"ajax": {
				"url": "/isard-admin/desktops/getAllTemplates/",
				"dataSrc": ""
			},

            "scrollY":        "125px",
            "scrollCollapse": true,
            "paging":         false,
            
            //~ "searching":         false,
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "zeroRecords":    "No matching templates found",
                "info":           "Showing _START_ to _END_ of _TOTAL_ templates",
                "infoEmpty":      "Showing 0 to 0 of 0 templates",
                "infoFiltered":   "(filtered from _MAX_ total templates)"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
				//~ {
                //~ "className":      'details-control',
                //~ "orderable":      false,
                //~ "data":           null,
                //~ "width": "10px",
                //~ "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				//~ },
                { "data": "kind", "width": "10px", "orderable": false},
				{ "data": "name"},
                { "data": "group", "width": "10px"},
                { "data": "username"}
				],
			 "order": [[0, 'asc']],	
             "pageLength": 5,	 
		"columnDefs": [     
                            {
							"targets": 0,
							"render": function ( data, type, full, meta ) {
							  return renderTemplateKind(full);
							}},
							{
							"targets": 1,
							"render": function ( data, type, full, meta ) {
							  return renderIcon1x(full)+" "+full.name;
							}},
							]



	} );  
    


        
    
    modal_add_desktops.columns().every( function () {
        var that = this;
 
        $( 'input', this.header() ).on( 'keyup change', function () {
            if ( that.search() !== this.value ) {
                that
                    .search( this.value )
                    .draw();
            }
        } );
    } );





}

function initalize_modal_all_desktops_events(){
   $('#modal_add_desktops tbody').on( 'click', 'tr', function () {
        rdata=modal_add_desktops.row(this).data()
        if ( $(this).hasClass('selected') ) {
            $(this).removeClass('selected');
            $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
            $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
            
            $('#modalAddDesktop #template').val('');
            $('#modalAddDesktop #btn-hardware').hide();
            $('#modalAddDesktop #hardware-block').hide();
        }
        else {
            modal_add_desktops.$('tr.selected').removeClass('selected');
            $(this).addClass('selected');
            $('#modal_add_desktops').closest('.x_panel').removeClass('datatables-error');
            $('#modalAddDesktop #datatables-error-status').empty().html('<b style="color:DarkSeaGreen">Template selected: '+rdata['name']+'</b>').removeClass('my-error');
            $('#modalAddDesktop #template').val(rdata['id']);
            //if(user['role']!='user'){
                $('#modalAddDesktop #btn-hardware').show();
                setHardwareDomainDefaults('#modalAddDesktop',rdata['id'])
            //}
        }
    } );	
	
    $("#modalAddDesktop #send").on('click', function(e){
        var form = $('#modalAdd');

        form.parsley().validate();

        if (form.parsley().isValid()){
            template=$('#modalAddDesktop #template').val();
            if (template !=''){
                data=$('#modalAdd').serializeObject();
                socket.emit('domain_add',data)
            }else{
                $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
            }
        }
    });
        
        $("#modalAddDesktop #btn-hardware").on('click', function(e){
                $('#modalAddDesktop #hardware-block').show();
        });



    $("#modalTemplateDesktop #send").on('click', function(e){
            var form = $('#modalTemplateDesktopForm');

            form.parsley().validate();

            if (form.parsley().isValid()){
                desktop_id=$('#modalTemplateDesktopForm #id').val();
                if (desktop_id !=''){
                    data=$('#modalTemplateDesktopForm').serializeObject();
                    data=replaceMedia_arrays('#modalTemplateDesktopForm',data);
                    data=replaceAlloweds_arrays('#modalTemplateDesktopForm #alloweds-add',data)
                    socket.emit('domain_template_add',data)
                }else{
                    $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                }
            }
        });
        
        //~ $("#modalAddDesktop #btn-hardware").on('click', function(e){
                //~ $('#modalAddDesktop #hardware-block').show();
        //~ });
        	
}

function modal_edit_desktop_datatables(id){
	$.ajax({
		type: "GET",
		url:"/isard-admin/desktops/templateUpdate/" + id,
		success: function(data)
		{
            $('#modalEditDesktop #forced_hyp').closest("div").remove();
			$('#modalEditDesktop #name_hidden').val(data.name);
            $('#modalEditDesktop #name').val(data.name);
			$('#modalEditDesktop #description').val(data.description);
            $('#modalEditDesktop #id').val(data.id);
            setHardwareDomainDefaults('#modalEditDesktop', id);
            if(data['options-viewers-spice-fullscreen']){
                $('#modalEditDesktop #options-viewers-spice-fullscreen').iCheck('check');
            }else{
                //~ $('#modalEditHyper #modalEdit #capabilities-disk_operations').iCheck('check');
            }
            //~ $('#modalEditDesktop #options-viewers-spice-fullscreen').iCheck('check');
		}				
	});
  
    
}

    $("#modalEditDesktop #send").on('click', function(e){
            var form = $('#modalEdit');
            form.parsley().validate();
            if (form.parsley().isValid()){
                    data=$('#modalEdit').serializeObject();
                    data=replaceMedia_arrays('#modalEditDesktop',data);
                    socket.emit('domain_edit',data)
            }
        });
        
    
