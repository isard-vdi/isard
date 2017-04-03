/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {
	
	$template = $(".template-detail");
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
			$('#modalAddDesktop').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
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
				//~ { "data": "description", "visible": false}
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
                if (!row.data().status.includes('Fail')){
                    setHardwareDomainDefaults_viewer('#hardware-'+row.data().id,row.data().id);
                }
                actionsDesktopDetail();
                setDesktopDetailButtonsStatus(row.data().id,row.data().status)
                setDomainGenealogy(row.data().id);
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
					//~ api.ajax('/domains/update','POST',{'pk':data['id'],'name':'status','value':'Starting'}).done(function(data) {
					//~ });  
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
							api.ajax('/domains/update','POST',{'pk':data['id'],'name':'status','value':'Stopping'}).done(function(data) {
                			}); 
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
					api.ajax('/desktops/viewer/xpi/'+data['id'],'GET',{}).done(function(data) {
                        if(data==false){
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
                            if(data.tlsport){
                                openTLS(data.host, data.port, data.tlsport, data.passwd, data.ca);
                            }else{
                                openTCP(data.host, data.port, data.passwd);
                            }
                        }
                    });                         
                    }
				}else{
					//Viewer .vv Download
					//~ api.ajax('/desktops/viewer/xpi/'+data['id'],'GET',{}).done(function(error) {
                    //~ if(error==false){
						//~ new PNotify({
						//~ title: "Display error",
							//~ text: "Can't download display file, something went wrong.",
							//~ hide: true,
							//~ delay: 3000,
							//~ icon: 'fa fa-alert-sign',
							//~ opacity: 1,
							//~ type: 'error'
						//~ });
					//~ }else{
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
                                            api.ajax('/desktops/viewer/html5/'+data['id'],'GET',{}).done(function(data) {
                                                notice.update({
                                                    title: 'You choosed HTML5', text: 'Opening in new window...', icon: true, type: 'info', hide: true,
                                                    confirm: {
                                                        confirm: false
                                                    },
                                                    buttons: {
                                                        closer: true,
                                                        sticker: false
                                                    }
                                                });
                                                http://vdesktop6.escoladeltreball.org/?host=isard-devel.escoladeltreball.org&port=55906&passwd=1234
                                                url='http://'+data.host+'/?host='+data.host+'&port='+data.port+'&passwd='+data.passwd
                                                window.open(url);
                                            }).fail(function (data) {
                                                notice.update({
                                                    title: 'Failed', text: 'Something went wrong...', icon: true, type: 'error', hide: true,
                                                    confirm: {
                                                        confirm: false
                                                    },
                                                    buttons: {
                                                        closer: true,
                                                        sticker: false
                                                    }
                                                });
                                                window.open('/desktops');
                                            });
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
    socket = io.connect('https://' + document.domain + ':' + location.port+'/domains');

    socket.on('connect', function() {
        connection_done();
        console.log('Listening user namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
    socket.on('user_quota', function(data) {
        console.log('Quota update')
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

    //~ socket.on('desktop_update', function(data){
        //~ console.log('update')
        //~ var data = JSON.parse(data);
        //~ var row = table.row('#'+data.id); 
        //~ table.row(row).data(data);
        //~ setDesktopDetailButtonsStatus(data.id, data.status);
    //~ });

    socket.on('desktop_data', function(data){
        console.log('add or update')
        var data = JSON.parse(data);
        //~ dtInsertUpdate(table,data,true)
        //~ console.log('done')
		if($("#" + data.id).length == 0) {
		  //it doesn't exist
		  table.row.add(data).draw();
		}else{
          //if already exists do an update (ie. connection lost and reconnect)
          var row = table.row('#'+data.id); 
          table.row(row).data(data).invalidate();			
		}
        table.draw(false);
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
    
    socket.on ('result', function (data) {
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
    
//~ // SERVER SENT EVENTS Stream
	//~ if (!!window.EventSource) {
	  //~ var desktops_source = new EventSource('/stream/desktops');
      //~ console.log('Listening desktops...');
	//~ } else {
	  //~ // Result to xhr polling :(
	//~ }

	//~ window.onbeforeunload = function(){
	  //~ desktops_source.close();
	//~ };

	//~ desktops_source.addEventListener('New', function(e) {
	  //~ var data = JSON.parse(e.data);
		//~ if($("#" + data.id).length == 0) {
		  //~ //it doesn't exist
		  //~ table.row.add(data).draw();
		//~ }else{
          //~ //if already exists do an update (ie. connection lost and reconnect)
          //~ var row = table.row('#'+data.id); 
          //~ table.row(row).data(data);			
		//~ }
	//~ }, false);

	//~ desktops_source.addEventListener('Status', function(e) {
	  //~ var data = JSON.parse(e.data);
          //~ var row = table.row('#'+data.id); 
          //~ table.row(row).data(data);
          //~ setDesktopDetailButtonsStatus(data.id, data.status);
          //~ console.log(data);
	//~ }, false);

	//~ desktops_source.addEventListener('Deleted', function(e) {
	  //~ var data = JSON.parse(e.data);
      //~ var row = table.row('#'+data.id).remove().draw();
            //~ new PNotify({
                //~ title: "Desktop deleted",
                //~ text: "Desktop "+data.name+" has been deleted",
                //~ hide: true,
                //~ delay: 4000,
                //~ icon: 'fa fa-success',
                //~ opacity: 1,
                //~ type: 'info'
            //~ });
	//~ }, false);

});


function actionsDesktopDetail(){
	$('.btn-edit').on('click', function () {
            //Not implemented
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
        return '<div class="Change"> <i class="fa fa-spinner fa-pulse fa-2x fa-fw"></i><span class="sr-only">Loading...</span></i> </div>';
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


