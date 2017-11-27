/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

socket=null
user={}
$(document).ready(function() {
    user['role']=$('#user-data').data("role");
    modal_add_desktops = $('#modal_add_desktops').DataTable()
	initalize_modal_all_desktops_events()
 
	$template = $(".template-detail-domain");

    
	$('.btn-new').on('click', function () {
		if($('.quota-desktops .perc').text() >=100){
            new PNotify({
                title: "Quota for creating desktops full.",
                text: "Can't create another desktop, quota full.",
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


	//DataTable Main renderer
	var table = $('#desktops').DataTable({
			"ajax": {
				"url": "/desktops/get",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
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
				{ "data": "name"},
                { "data": "hyp_started", "width": "10px"}
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
							  return renderStatus(full);
							}},
							{
							"targets": 5,
							"render": function ( data, type, full, meta ) {
							  return renderName(full);
							}},
							{
							"targets": 6,
							"render": function ( data, type, full, meta ) {
							  return renderHypStarted(full);
							}}
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
                row.child( addDesktopDetailPannel(row.data()) ).show();
                tr.addClass('shown');
                $('#status-detail-'+row.data().id).html(row.data().detail);
                actionsDesktopDetail();
                setDesktopDetailButtonsStatus(row.data().id,row.data().status)
                if(row.data().status=='Stopped' || row.data().status=='Started'){
                    setDomainGenealogy(row.data().id);
                    setHardwareDomainDefaults_viewer('#hardware-'+row.data().id,row.data().id);
                }                
                
               
                
            }
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
							stack: stack_center
						}).get().on('pnotify.confirm', function() {
                            socket.emit('domain_update',{'pk':data['id'],'name':'status','value':'Stopping'})
						}).on('pnotify.cancel', function() {
				});	
                break;
            case 'btn-display':
				if(detectXpiPlugin()){
					//SPICE-XPI Plugin
                    console.log('xpi detected')
                    if(isXpiBlocked()){
                            new PNotify({
                            title: "Plugin blocked",
                                text: "You should allow SpiceXPI plugin and then reload webpage.",
                                hide: true,
                                confirm: {
                                    confirm: true,
                                    cancel: false
                                },
                                //~ delay: 3000,
                                icon: 'fa fa-alert-sign',
                                opacity: 1,
                                type: 'warning'
                            });                        
                    }else{
                    socket.emit('domain_viewer',{'pk':data['id'],'kind':'xpi'})                       
                    }
				}else{
                        new PNotify({
                            title: 'Choose display connection',
                            text: 'Open in browser (html5) or download remote-viewer file.',
                            icon: 'glyphicon glyphicon-question-sign',
                            hide: false,
                            delay: 3000,
                            confirm: {
                                confirm: true,
                                buttons: [
                                    {
                                        text: 'HTML5',
                                        addClass: 'btn-primary',
                                        click: function(notice){
                                            notice.update({
                                                title: 'You choosed html5 viewer', text: 'Viewer will be opened in new window.\n Please allow popups!', icon: true, type: 'info', hide: true,
                                                confirm: {
                                                    confirm: false
                                                },
                                                buttons: {
                                                    closer: true,
                                                    sticker: false
                                                }
                                            });                                            
                                            socket.emit('domain_viewer',{'pk':data['id'],'kind':'html5'});
                                        }
                                    },
                                    {
                                        text: 'Download display file',
                                        click: function(notice){
                                            notice.update({
                                                title: 'You choosed to download', text: 'File will be downloaded shortly', icon: true, type: 'info', hide: true,
                                                confirm: {
                                                    confirm: false
                                                },
                                                buttons: {
                                                    closer: true,
                                                    sticker: false
                                                }
                                            });
                                            //~ socket.emit('domain_viewer',{'pk':data['id'],'kind':'file'});
                                            
                                                var url = '/desktops/viewer/file/'+data['id'];
                                                var anchor = document.createElement('a');
                                                    anchor.setAttribute('href', url);
                                                    anchor.setAttribute('download', 'console.vv');
                                                var ev = document.createEvent("MouseEvents");
                                                    ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
                                                    anchor.dispatchEvent(ev);                                              
                                        }
                                    },
                                ]
                            },
                            buttons: {
                                closer: false,
                                sticker: false
                            },
                            history: {
                                history: false
                            }
                        });                        


					}
				//~ }); 
				//~ }
                break;
        }
    });


    // SocketIO
    reconnect=-1;
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_users');
    console.log(socket)
     
    socket.on('connect', function() {
        connection_done();
        reconnect+=1;
        if(reconnect){
            console.log(reconnect+' reconnects to websocket. Refreshing datatables');
            table.ajax.reload();
            // Should have a route to update quota via ajax...
        }
        console.log('Listening users namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
    socket.on('user_quota', function(data) {
        console.log('Quota update')
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

    socket.on('desktop_data', function(data){
        console.log('add or update')
        var data = JSON.parse(data);
        dtUpdateInsert(table,data,false);
        setDesktopDetailButtonsStatus(data.id, data.status);
    });
    
    socket.on('desktop_delete', function(data){
        console.log('delete')
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
        console.log('received result')
        var data = JSON.parse(data);
        if(data.result){
            $("#modalAdd")[0].reset();
            $("#modalAddDesktop").modal('hide');
            //~ $('body').removeClass('modal-open');
            //~ $('.modal-backdrop').remove();
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
        
    socket.on('domain_viewer', function (data) {
        var data = JSON.parse(data);
        console.log('domain_viewer event received'+data)
        if(data['kind']=='xpi'){
            viewer=data['viewer']
                        if(viewer==false){
                            new PNotify({
                            title: "Display error",
                                text: "Can't open display, something went wrong.",
                                hide: true,
                                delay: 3000,
                                icon: 'fa fa-alert-sign',
                                opacity: 1,
                                type: 'error'
                            });
                        }else{
                            if(viewer.tlsport){
                                openTLS(viewer.host, viewer.port, viewer.tlsport, viewer.passwd, viewer.ca);
                            }else{
                                openTCP(viewer.host, viewer.port, viewer.passwd);
                            }
                        }
        }
        if(data['kind']=='html5'){
            viewer=data['viewer']
            //~ window.open('http://try.isardvdi.com:8000/?host=try.isardvdi.com&port='+viewer.port+'&passwd='+viewer.passwd); 
            window.open('http://'+viewer.host+'/?host='+viewer.host+'&port='+viewer.port+'&passwd='+viewer.passwd);            
            
        }        
        
         if(data['kind']=='file'){
            //~ viewer=data['viewer']
            var url = '/desktops/viewer/file/'+data['id'];
            var anchor = document.createElement('a');
                anchor.setAttribute('href', url);
                anchor.setAttribute('download', 'console.vv');
            var ev = document.createEvent("MouseEvents");
                ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
                anchor.dispatchEvent(ev);        
        }
    });

});


function actionsDesktopDetail(){
	$('.btn-edit').on('click', function () {
            var pk=$(this).closest("div").attr("data-pk");
            console.log(pk)
			setHardwareOptions('#modalEditDesktop');
            $("#modalEdit")[0].reset();
			$('#modalEditDesktop').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
             $('#hardware-block').hide();
            $('#modalEdit').parsley();
            modal_edit_desktop_datatables(pk);
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
			var pk=$(this).closest("div").attr("data-pk");
			setDefaultsTemplate(pk);
			setHardwareOptions('#modalTemplateDesktop');
			setHardwareDomainDefaults('#modalTemplateDesktop',pk);
			$('#modalTemplateDesktop').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
        }
	});

	$('.btn-delete').on('click', function () {
				var pk=$(this).closest("div").attr("data-pk");
				var name=$(this).closest("div").attr("data-name");
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
							stack: stack_center
						}).get().on('pnotify.confirm', function() {
                            socket.emit('domain_update',{'pk':pk,'name':'status','value':'Deleting'})
						}).on('pnotify.cancel', function() {
				});	
	});
}
	
//~ RENDER DATATABLE	
function addDesktopDetailPannel ( d ) {
		$newPanel = $template.clone();
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

function renderStatus(data){
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
        return '<i class="fa fa-spinner fa-pulse fa-2x fa-fw"></i>';
}	

function renderHypStarted(data){
        if('hyp_started' in data){ return data.hyp_started;}
		return '';
}

function setDefaultsTemplate(id) {
	$.ajax({
		type: "GET",
		url:"/desktops/templateUpdate/" + id,
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
		if(data.kind=="public_template"){return "public";}
        if(data.kind=="user_template"){return "private";}
        return "base"
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
				"url": "/desktops/getAllTemplates",
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




//~ window.ParsleyConfig = {
    //~ excluded: 'input[type=button], input[type=submit], input[type=reset]',
    //~ inputs: 'input, textarea, select, input[type=hidden], :hidden',
//~ };

}

function initalize_modal_all_desktops_events(){
   $('#modal_add_desktops tbody').on( 'click', 'tr', function () {
        rdata=modal_add_desktops.row(this).data()
        console.log($(this).hasClass('selected'))
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
            if(user['role']!='user'){
                $('#modalAddDesktop #btn-hardware').show();
                setHardwareDomainDefaults('#modalAddDesktop',rdata['id'])
            }
        }
    } );	
	
    $("#modalAddDesktop #send").on('click', function(e){
            var form = $('#modalAdd');

            form.parsley().validate();

            if (form.parsley().isValid()){
                template=$('#modalAddDesktop #template').val();
                console.log('TEMPLATE:'+template)
                if (template !=''){
                    data=$('#modalAdd').serializeObject();
                    console.log(data)
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
        	
}
function modal_edit_desktop_datatables(id){
	$.ajax({
		type: "GET",
		url:"/desktops/templateUpdate/" + id,
		success: function(data)
		{
            console.log(data)
			$('#modalEditDesktop #name').val(data.name);
			$('#modalEditDesktop #description').val(data.description);
            //~ $('#modalEditDesktop #datatables-error-status').val(data);
		}				
	});
    
}
    
