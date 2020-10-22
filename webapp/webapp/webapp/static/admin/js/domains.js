/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var href = location.href;
url=href.match(/([^\/]*)\/*$/)[1];
if(url!="Desktops"){kind='template';}else{$('#global_actions').css('display','block');kind='desktop';}

columns= [
				{
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
				{ "data": "icon" },
                { "data": "hyp_started", "width": "10px"},
				{ "data": "name"},
				{ "data": null},
				{ "data": "status"},
				{ "data": "kind"},
				{ "data": "username"},
				{ "data": "category"},
				{ "data": "group"},
                { "data": "accessed",
                 'defaultContent': ''},
                ]
if(url!="Desktops"){
    columns.push({"data": "derivates"});
}

$(document).ready(function() {
    $('.admin-status').show()
    $template_domain = $(".template-detail-domain");
    $admin_template_domain = $(".admin-template-detail-domain");

    var stopping_timer=null

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
        
    $("#modalDeleteTemplate #send").on('click', function(e){

        selected = $("#modalDeleteTemplate .tree_template_delete").fancytree('getTree').getSelectedNodes();
        todelete = []
        selected.forEach(function (item) {
            todelete.push({"id":item.data.id, "title":item.title, "kind":item.data.kind, "status":item.data.status})
        });        
        //id=$('#modalDeleteTemplate #id').val();
        api.ajax('/isard-admin/admin/items/delete','POST',todelete).done(function(data) {
            data=JSON.parse(data);
            if( data == true ){
                new PNotify({
                        title: "Deleting",
                        text: "Deleting all templates and desktops",
                        hide: true,
                        delay: 4000,
                        icon: 'fa fa-success',
                        opacity: 1,
                        type: 'success'
                });                                
            }else{
                new PNotify({
                        title: "Error deleting",
                        text: "Unable to delete templates and desktops: "+data,
                        hide: true,
                        delay: 4000,
                        icon: 'fa fa-warning',
                        opacity: 1,
                        type: 'error'
                });                                
            }
            domains_table.ajax.reload()
            $("#modalDeleteTemplate").modal('hide');                
        });
             
    });


    // Setup - add a text input to each footer cell
    $('#domains tfoot th').each( function () {
        var title = $(this).text();
        if (['','Icon','Hypervisor','Action'].indexOf(title) == -1){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );
            
		domains_table= $('#domains').DataTable({
			"ajax": {
				"url": "/isard-admin/admin/domains/get/"+url,
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
			"deferRender": true,
			"columns": columns,
			 "order": [[4, 'asc']],
			 "columnDefs": [ {
							"targets": 1,
							"render": function ( data, type, full, meta ) {
							  return renderIcon(full);
							}},
							//~ {
							//~ "targets": 3,
							//~ "render": function ( data, type, full, meta ) {
							  //~ return renderName(full);
							//~ }},
							{
							"targets": 4,
                            "width": "100px",
							"render": function ( data, type, full, meta ) {
							  return renderAction(full)+renderDisplay(full);
							}},
							{
							"targets": 5,
							"render": function ( data, type, full, meta ) {
							  return renderStatus(full);
							}},
							{
							"targets": 10,
							"render": function ( data, type, full, meta ) {
                              if ( type === 'display' || type === 'filter' ) {
                                  return moment.unix(full.accessed).fromNow();
                              }  
                              return full.accessed;                                 
							  //~ return moment.unix(full.accessed).toISOString("YYYY-MM-DDTHH:mm"); //moment.unix(full.accessed).fromNow();
							}},
                            {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
							  return renderHypStarted(full);
							}}
							]
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
    
    domains_table.on( 'click', 'tr', function () {
        $(this).toggleClass('active');
    } );

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
							api.ajax('/isard-admin/admin/mdomains','POST',{'ids':ids,'action':action}).done(function(data) {
                                $('#mactions option[value="none"]').prop("selected",true);
                			}); 
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
                setDomainDetailButtonsStatus(row.data().id,row.data().status)
                //if(row.data().status=='Stopped' || row.data().status=='Started' || row.data().status=='Failed'){
                    //~ setDomainGenealogy(row.data().id);
                    setHardwareDomainDefaults_viewer('#hardware-'+row.data().id,row.data());
                    if(url!="Desktops"){
                        setAlloweds_viewer('#alloweds-'+row.data().id,row.data().id);
                        //~ setDomainDerivates(row.data().id);
                    }
                //}
            }            
        }
    } );	


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
                    socket.emit('domain_update',{'pk':data['id'],'name':'status','value':'Starting'})
					//~ api.ajax('/isard-admin/domains/update','POST',{'pk':data['id'],'name':'status','value':'Starting'}).done(function(data) {
					//~ });  
				}          
                break;
            case 'btn-stop':
                socket.emit('domain_update',{'pk':data['id'],'name':'status','value':'Stopping'})
				//~ new PNotify({
						//~ title: 'Unplug desktop warning!',
							//~ text: "It is NOT RECOMMENDED to continue and turn off desktop "+ name+".\n \
								   //~ Please, properly shut down desktop from inside viewer \n\n \
								   //~ Turn off desktop? "+ name+"?",
							//~ hide: false,
							//~ opacity: 0.9,
							//~ confirm: {
								//~ confirm: true
							//~ },
							//~ buttons: {
								//~ closer: false,
								//~ sticker: false
							//~ },
							//~ history: {
								//~ history: false
							//~ },
							//~ addclass: 'pnotify-center'
						//~ }).get().on('pnotify.confirm', function() {
							//~ api.ajax('/isard-admin/domains/update','POST',{'pk':data['id'],'name':'status','value':'Stopping'}).done(function(data) {
                			//~ }); 
						//~ }).on('pnotify.cancel', function() {
				//~ });	
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
                            setViewerButtons(data['id'],socket);

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
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/isard-admin/sio_admins');

    socket.on('connect', function() {
        connection_done();
        socket.emit('join_rooms',['domains'])
        console.log('Listening admins namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
    startClientViewerSocket(socket);
    
    socket.on('user_quota', function(data) {
        console.log('Quota update')
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

    socket.on(kind+'_data', function(data){
        var data = JSON.parse(data);
        dtUpdateInsert(domains_table,data,false);
        setDomainDetailButtonsStatus(data.id, data.status);
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
            $("#modalAddFromBuilder #modalAdd")[0].reset();
            $("#modalAddFromBuilder").modal('hide');
            $("#modalAddFromMedia #modalAdd")[0].reset();
            $("#modalAddFromMedia").modal('hide');   
            $("#modalTemplateDesktop #modalTemplateDesktopForm")[0].reset();
            $("#modalTemplateDesktop").modal('hide');             
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
    
    socket.on('edit_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $("#modalEdit")[0].reset();
            $("#modalEditDesktop").modal('hide');
            $("#modalBulkEditForm")[0].reset();
            $("#modalBulkEdit").modal('hide');            
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

function actionsDomainDetail(){
    
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
                url:"/isard-admin/admin/domains/xml/" + pk,
                success: function(data)
                {
                    var data = JSON.parse(data);
                    $('#modalEditXmlForm #xml').val(data);
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
                    $('#modalShowInfoForm #xml').val(JSON.stringify(data, undefined, 4));
                }				
            });
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
                    //~ var data = JSON.parse(data);
                    $('#modalShowInfoForm #xml').val(JSON.stringify(data, undefined, 4));
                }				
            });
	});	    

    if(url=="Desktops"){
        $('.btn-delete-template').remove()
        //~ $('.btn-template').on('click', function () {
            //~ if($('.quota-templates .perc').text() >=100){
                //~ new PNotify({
                    //~ title: "Quota for creating templates full.",
                    //~ text: "Can't create another template, quota full.",
                    //~ hide: true,
                    //~ delay: 3000,
                    //~ icon: 'fa fa-alert-sign',
                    //~ opacity: 1,
                    //~ type: 'error'
                //~ });
            //~ }else{	
                //~ var pk=$(this).closest("[data-pk]").attr("data-pk");
                //~ setDefaultsTemplate(pk);
                //~ setHardwareOptions('#modalTemplateDesktop');
                //~ setHardwareDomainDefaults('#modalTemplateDesktop',pk);
                //~ $('#modalTemplateDesktop').modal({
                    //~ backdrop: 'static',
                    //~ keyboard: false
                //~ }).modal('show');
            //~ }
        //~ });

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
                                socket.emit('domain_update',{'pk':pk,'name':'status','value':'Deleting'})
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
            //delete_templates(pk);
            populate_tree_template_delete(pk);
        });
        
    }
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

function setDomainDetailButtonsStatus(id,status){
          //~ if(status=='Stopped'){
                //~ $('#actions-'+id+' *[class^="btn"]').prop('disabled', false);
          //~ }else{
                //~ $('#actions-'+id+' *[class^="btn"]').prop('disabled', true);
          //~ }
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
        if(data.status=='Stopping' || data.status =='Started'){
            return '<button type="button" id="btn-display" class="btn btn-pill-right btn-success btn-xs"> \
					<i class="fa fa-desktop"></i> Show</button>';
        }
        return ''
}

//~ function renderName(data){
		//~ return '<div class="block_content" > \
      			//~ <h2 class="title" style="height: 4px; margin-top: 0px;"> \
                //~ <a>'+data.name+'</a> \
                //~ </h2> \
      			//~ <p class="excerpt" >'+data.description+'</p> \
           		//~ </div>'
//~ }
                        
function renderIcon(data){
		return '<span class="xe-icon" data-pk="'+data.id+'">'+icon(data)+'</span>'
}

function renderStatus(data){
		return data.status;
}

function renderHypStarted(data){
        if('forced_hyp' in data && data.forced_hyp!=''){return '**'+data.forced_hyp+'**';}
        if('hyp_started' in data){ return data.hyp_started;}
		return '';
}

function renderAction(data){
		status=data.status;
        if(status=='Crashed'){
            return '<div class="Change"> <i class="fa fa-thumbs-o-down fa-2x"></i> </div>';
        } 
        if(status=='Stopped' || status=='Failed'){
            if(url=='Desktops'){
                return '<button type="button" id="btn-play" class="btn btn-pill-right btn-success btn-xs"><i class="fa fa-play"></i> Start</button>';
            }else{
                return '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button>';
            }
        }
        if(status=='Started'){
            if(url=='Desktops'){
                return '<button type="button" id="btn-stop" class="btn btn-pill-left btn-danger btn-xs"><i class="fa fa-stop"></i> Stop</button>';
            }else{
                return '<i class="fa fa-stop"></i>';
            }
        } 

        if(status=='Disabled' || status =='Manteinance'){
                return '<i class="fa fa-times fa-2x"></i>';
        }         
        return '<i class="fa fa-spinner fa-pulse fa-2x fa-fw"></i>';        
}	


function populate_tree_template_delete(id){

    $("#modalDeleteTemplate .tree_template_delete").fancytree({
        extensions: ["table"],
        table: {
          indentation: 20,      // indent 20px per node level
          nodeColumnIdx: 2,     // render the node title into the 2nd column
          checkboxColumnIdx: 0  // render the checkboxes into the 1st column
        },  
        source: {url: "/isard-admin/admin/domains/tree_list/" + id,
                cache: false},
        lazyLoad: function(event, data){
            data.result = $.ajax({
                url: "/isard-admin/admin/domains/tree_list/" + id,
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


function delete_templates(id){
    //~ var pk=$(this).closest("[data-pk]").attr("data-pk");
    $('#modalDeleteTemplate #id').val(id);
	modal_delete_templates = $('#modal_delete_templates').DataTable({
			"ajax": {
				"url": "/isard-admin/admin/domains/todelete/"+id,
				"dataSrc": ""
			},
            "scrollY":        "125px",
            "scrollCollapse": true,
            "paging":         false,
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
				{ "data": "kind"},
                { "data": "user"},
                { "data": "status"},
                { "data": "name"},
				],
			 //~ "order": [[0, 'asc']],	
             "pageLength": 10,	
             "destroy" : true 
	} );  
    
  
}

// MODAL EDIT DESKTOP
function modal_edit_desktop_datatables(id){
	$.ajax({
		type: "GET",
		url:"/isard-admin/desktops/templateUpdate/" + id,
		success: function(data)
		{
			$('#modalEditDesktop #name_hidden').val(data.name);
            $('#modalEditDesktop #name').val(data.name);
			$('#modalEditDesktop #description').val(data.description);
            $('#modalEditDesktop #id').val(data.id);
            setHardwareDomainDefaults('#modalEditDesktop', id);
		}				
	});
}
    $("#modalEditDesktop #send").on('click', function(e){
            var form = $('#modalEdit');
            form.parsley().validate();
            if (form.parsley().isValid()){
                    data=$('#modalEdit').serializeObject();
                    socket.emit('domain_edit',data)
            }
        });

    $("#modalEditXml #send").on('click', function(e){
            var form = $('#modalEditXmlForm');
            //~ form.parsley().validate();
            //~ if (form.parsley().isValid()){
                    id=$('#modalEditXmlForm #id').val();
                    xml=$('#modalEditXmlForm #xml').val();
                    api.ajax('/isard-admin/admin/domains/xml/'+id,'POST',{'xml':xml}).done(function(data) {
                        $("#modalEditXmlForm")[0].reset();
                        $("#modalEditXml").modal('hide');
                	}); 
            //~ }
        });

//~ }
