/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$(document).ready(function() {
	//~ $('#test').on( 'click', function () {
		//~ data={'id':'_eea1554300_LOGO','id2':'_cpr585864606_QWERTT','id3':'_isx47893266_ServerJournal'}
		//~ console.log('Invisible: '+domains_table.row('#'+data.id).id())
		//~ console.log('Visible tb: '+domains_table.row('#'+data.id3).id())
		//~ console.log('Inexistent: '+domains_table.row('#xxxyyy').id())
		//~ if(typeof(domains_table.row('#'+data.id3).id())=='undefined'){console.log('nulo')}else{console.log('gueno')}
		//~ if(typeof(domains_table.row('#xxxyyy').id())=='undefined'){console.log('nulo')}else{console.log('gueno')}
	//~ });
    modal_add_builder = $('#modal_add_builder').DataTable()
	initialize_modal_all_builder_events()

    modal_add_install = $('#modal_add_install').DataTable()
	initialize_modal_all_install_events()

    modal_add_isos = $('#modal_add_isos').DataTable()
	initialize_modal_all_isos_events()
           
	$('.add-new-virtbuilder').on( 'click', function () {
                                //~ //Remove when engine does the job
                                    //~ api.ajax('/admin/domains/virtrebuild','GET',{}).done(function(data) {
                                                //~ console.log(data)
                                                    //~ });  
			setHardwareOptions('#modalAddFromBuilder');
            $("#modalAddFromBuilder #modalAdd")[0].reset();
			$('#modalAddFromBuilder').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalAddFromBuilder #modalAdd').parsley();
            modal_add_builder_datatables();
            //~ modal_add_install_datatables();
            //~ modal_add_isos_datatables();
	});

	$('.add-new-iso').on( 'click', function () {
                                //~ //Remove when engine does the job
                                    //~ api.ajax('/admin/domains/virtrebuild','GET',{}).done(function(data) {
                                                //~ console.log(data)
                                                    //~ });  
			setHardwareOptions('#modalAddFromIso');
            $("#modalAddFromIso #modalAdd")[0].reset();
			$('#modalAddFromIso').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalAddFromIso #modalAdd').parsley();
            //~ modal_add_builder_datatables();
            modal_add_install_datatables();
            modal_add_isos_datatables();
	});




        $template_domain = $(".template-detail-domain");

    // Setup - add a text input to each footer cell
    $('#domains tfoot th').each( function () {
        var title = $(this).text();
        if (['','Icon','Hypervisor','Action'].indexOf(title) == -1){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );
            
		domains_table= $('#domains').DataTable({
			"ajax": {
				"url": "/admin/domains/get",
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
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
				{ "data": "icon" },
                { "data": "hyp_started", "width": "10px"},
				{ "data": "name"},
				{ "data": null},
				{ "data": "status"},
				{ "data": "kind"},
				{ "data": "user"},
				{ "data": "category"},
				{ "data": "group"},
                { "data": "accessed"}],
			 "order": [[4, 'asc']],
			 "columnDefs": [ {
							"targets": 1,
							"render": function ( data, type, full, meta ) {
							  return renderIcon(full);
							}},
							{
							"targets": 3,
							"render": function ( data, type, full, meta ) {
							  return renderName(full);
							}},
							{
							"targets": 4,
							"render": function ( data, type, full, meta ) {
							  return renderAction(full);
							}},
							{
							"targets": 5,
							"render": function ( data, type, full, meta ) {
							  return renderStatus(full);
							}},
							{
							"targets": 10,
							"render": function ( data, type, full, meta ) {
							  return moment.unix(full.accessed).toISOString("YYYY-MM-DDTHH:mm"); //moment.unix(full.accessed).fromNow();
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
							stack: stack_center
						}).get().on('pnotify.confirm', function() {
							api.ajax('/admin/mdomains','POST',{'ids':ids,'action':action}).done(function(data) {
                			}); 
						}).on('pnotify.cancel', function() {
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
                if (!row.data().status.includes('Fail')){
                    setHardwareDomainDefaults_viewer('#hardware-'+row.data().id,row.data().id);
                }
                actionsDomainDetail();
                setDomainGenealogy(row.data().id);
                //~ setDomainDetailButtonsStatus(row.data().id,row.data().status)
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
					api.ajax('/domains/update','POST',{'pk':data['id'],'name':'status','value':'Starting'}).done(function(data) {
					});  
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
				}else{
					//Viewer .vv Download
					api.ajax('/desktops/viewer/xpi/'+data['id'],'GET',{}).done(function(error) {
                    if(error==false){
						new PNotify({
						title: "Display error",
							text: "Can't download display file, something went wrong.",
							hide: true,
							delay: 3000,
							icon: 'fa fa-alert-sign',
							opacity: 1,
							type: 'error'
						});
					}else{
						var url = '/desktops/viewer/file/'+data['id'];
						var anchor = document.createElement('a');
							anchor.setAttribute('href', url);
							anchor.setAttribute('download', 'console.vv');
						var ev = document.createEvent("MouseEvents");
							ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
						anchor.dispatchEvent(ev);
					}
				}); 
				}
                break;
        }
    });	


    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_admins');

    socket.on('connect', function() {
        connection_done();
        socket.emit('join_rooms',['domains'])
        console.log('Listening admins namespace');
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
        var data = JSON.parse(data);
        dtUpdateInsert(domains_table,data,false);
        //~ applyData(domains_table,data,false)
		//~ if($("#" + data.id).length == 0) {
		  //~ //it doesn't exist
		  //~ domains_table.row.add(data).draw();
		//~ }else{
          //~ //if already exists do an update (ie. connection lost and reconnect)
          //~ var row = domains_table.row('#'+data.id); 
          //~ domains_table.row(row).data(data).invalidate();			
		//~ }
        //~ domains_table.draw(false);
        setDomainDetailButtonsStatus(data.id, data.status);
    });
    
    socket.on('desktop_delete', function(data){
        console.log('delete')
        var data = JSON.parse(data);
        var row = domains_table.row('#'+data.id).remove().draw();
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


    //~ // Stream domains_source
	//~ if (!!window.EventSource) {
	  //~ var domains_source = new EventSource('/admin/stream/domains');
      //~ console.log('Listening domains...');
	//~ } else {
	  // Result to xhr polling :(
	//~ }

	//~ window.onbeforeunload = function(){
	  //~ domains_source.close();
	//~ };

	//~ domains_source.addEventListener('open', function(e) {
	  //~ // Connection was opened.
	//~ }, false);

	//~ domains_source.addEventListener('error', function(e) {
	  //~ if (e.readyState == EventSource.CLOSED) {
		//~ // Connection was closed.
	  //~ }
     
	//~ }, false);

	//~ domains_source.addEventListener('New', function(e) {
	  //~ var data = JSON.parse(e.data);
		//~ if($("#" + data.id).length == 0) {
		  //~ //it doesn't exist
		  //~ domains_table.row.add(data).draw();
            //~ new PNotify({
                //~ title: "Domain added",
                //~ text: "Domain "+data.name+" has been created",
                //~ hide: true,
                //~ delay: 2000,
                //~ icon: 'fa fa-success',
                //~ opacity: 1,
                //~ type: 'success'
            //~ });          
		//~ }else{
          //~ //if already exists do an update (ie. connection lost and reconnect)
          //~ var row = table.row('#'+data.id); 
          //~ domains_table.row(row).data(data);			
		//~ }
	//~ }, false);

	//~ domains_source.addEventListener('Status', function(e) {
          //~ var data = JSON.parse(e.data);
          //~ var row = domains_table.row('#'+data.id); 
          //~ domains_table.row(row).data(data);
          //~ setDomainDetailButtonsStatus(data.id, data.status);
	//~ }, false);

	//~ domains_source.addEventListener('Deleted', function(e) {
	  //~ var data = JSON.parse(e.data);
      //~ var row = table.row('#'+data.id).remove().draw();
            //~ new PNotify({
                //~ title: "Domain deleted",
                //~ text: "Domain "+data.name+" has been deleted",
                //~ hide: true,
                //~ delay: 2000,
                //~ icon: 'fa fa-success',
                //~ opacity: 1,
                //~ type: 'info'
            //~ });
	//~ }, false);
    
});

function actionsDomainDetail(){
    
	$('.btn-edit').on('click', function () {
            //Not implemented
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
							api.ajax('/domains/update','POST',{'pk':pk,'name':'status','value':'Deleting'}).done(function(data) {
                                //Should return something about the result...
							});  
						}).on('pnotify.cancel', function() {
				});	
	});
    
}

//~ RENDER DATATABLE	
function addDomainDetailPannel ( d ) {
		$newPanel = $template_domain.clone();
		$newPanel.html(function(i, oldHtml){
			return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name);
		});
		return $newPanel
}

function setDomainDetailButtonsStatus(id,status){
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

function renderHypStarted(data){
        if('hyp_started' in data){ return data.hyp_started;}
		return '';
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




// MODAL BUILDER FUNCTIONS
function initialize_modal_all_builder_events(){
   $('#modal_add_builder tbody').on( 'click', 'tr', function () {
        rdata=modal_add_builder.row(this).data()
        console.log($(this).hasClass('selected'))
        if ( $(this).hasClass('selected') ) {
            $(this).removeClass('selected');
            $('#modal_add_builder').closest('.x_panel').addClass('datatables-error');
            $('#modalBuilder #datatables-error-status').html('No template selected').addClass('my-error');
            
            $('#modalBuilder #builder').val('');
            //~ $('#modalBuilder #btn-hardware').hide();
            //~ $('#modalBuilder #hardware-block').hide();
        }
        else {
            modal_add_builder.$('tr.selected').removeClass('selected');
            $(this).addClass('selected');
            $('#modal_add_builder').closest('.x_panel').removeClass('datatables-error');
            $('#modalBuilder #datatables-error-status').empty().html('<b style="color:DarkSeaGreen">Template selected: '+rdata['name']+'</b>').removeClass('my-error');
            $('#modalBuilder #builder').val(rdata['id']);
                //~ $('#modalAddFromBuilder #btn-hardware').show();
                //~ setHardwareDomainDefaults('#modalAddFromBuilder',rdata['id'])
        }
    } );	
        
        //~ $("#modalBuilder #btn-hardware").on('click', function(e){
                //~ $('#modalBuilder #hardware-block').show();
        //~ });

    $("#modalAddFromBuilder #send").on('click', function(e){
            var form = $('#modalAddFromBuilder #modalAdd');
            console.log('inside')
            //~ form.parsley().validate();
            //~ var queryString = $('#modalAdd').serialize();
            data=$('#modalAddFromBuilder #modalAdd').serializeObject();
            console.log(data)
            socket.emit('domain_virtbuilder_add',data)
            //~ if (form.parsley().isValid()){
                //~ template=$('#modalAddDesktop #template').val();
                //~ console.log('TEMPLATE:'+template)
                //~ if (template !=''){
                    //~ var queryString = $('#modalAdd').serialize();
                    //~ data=$('#modalAdd').serializeObject();
                    //~ socket.emit('domain_add',data)
                //~ }else{
                    //~ $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    //~ $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                //~ }
            //~ }
        });
        
}

function modal_add_builder_datatables(){
    modal_add_builder.destroy()
    $('#modalBuilder #builder').val('');
    $('#modalBuilder #datatables-error-status').empty()
    
    $('#modal_add_builder thead th').each( function () {
        var title = $(this).text();
        if(title=='Name'){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );
    
	modal_add_builder = $('#modal_add_builder').DataTable({
			"ajax": {
				"url": "/admin/table/domains_virt_builder/get",
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
				{ "data": "name"},
                { "data": "arch"},
                { "data": "revision"},
                { "data": "size"},
                { "data": "compressed_size"}
				],
			 "order": [[0, 'asc']],	
             "pageLength": 10,	 
	} );  

    modal_add_builder.columns().every( function () {
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



// MODAL install FUNCTIONS
function initialize_modal_all_install_events(){
   $('#modal_add_install tbody').on( 'click', 'tr', function () {
        rdata=modal_add_install.row(this).data()
        console.log($(this).hasClass('selected'))
        if ( $(this).hasClass('selected') ) {
            $(this).removeClass('selected');
            $('#modal_add_install').closest('.x_panel').addClass('datatables-error');
            $('#modalInstall #datatables-error-status').html('No template selected').addClass('my-error');
            
            $('#modalInstall #install').val('');
            //~ $('#modalInstall #btn-hardware').hide();
            //~ $('#modalInstall #hardware-block').hide();
        }
        else {
            modal_add_install.$('tr.selected').removeClass('selected');
            $(this).addClass('selected');
            $('#modal_add_install').closest('.x_panel').removeClass('datatables-error');
            $('#modalInstall #datatables-error-status').empty().html('<b style="color:DarkSeaGreen">Template selected: '+rdata['name']+'</b>').removeClass('my-error');
            $('#modalInstall #install').val(rdata['id']);
                //~ $('#modalAddInstall #btn-hardware').show();
                //~ setHardwareDomainDefaults('#modalAddInstall',rdata['id'])
        }
    } );	
        	
}

function modal_add_install_datatables(){
    modal_add_install.destroy()
    $('#modalInstall #install').val('');
    $('#modalInstall #datatables-error-status').empty()
    
    $('#modal_add_install thead th').each( function () {
        var title = $(this).text();
        if(title=='Name'){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );
    
	modal_add_install = $('#modal_add_install').DataTable({
			"ajax": {
				"url": "/admin/table/domains_virt_install/get",
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
				{ "data": "name"},
                { "data": "vers"},
				],
			 "order": [[0, 'asc']],	
             "pageLength": 10,	 
	} );  

    modal_add_install.columns().every( function () {
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



// MODAL BUILDER FUNCTIONS
function initialize_modal_all_isos_events(){
   $('#modal_add_isos tbody').on( 'click', 'tr', function () {
        rdata=modal_add_isos.row(this).data()
        console.log($(this).hasClass('selected'))
        if ( $(this).hasClass('selected') ) {
            $(this).removeClass('selected');
            $('#modal_add_isos').closest('.x_panel').addClass('datatables-error');
            $('#modalIsos #datatables-error-status').html('No template selected').addClass('my-error');
            
            $('#modalIsos #iso').val('');
            //~ $('#modalIsos #btn-hardware').hide();
            //~ $('#modalIsos #hardware-block').hide();
        }
        else {
            modal_add_isos.$('tr.selected').removeClass('selected');
            $(this).addClass('selected');
            $('#modal_add_isos').closest('.x_panel').removeClass('datatables-error');
            $('#modalIsos #datatables-error-status').empty().html('<b style="color:DarkSeaGreen">Template selected: '+rdata['name']+'</b>').removeClass('my-error');
            $('#modalIsos #iso').val(rdata['id']);
                //~ $('#modalAddFromBuilder #btn-hardware').show();
                //~ setHardwareDomainDefaults('#modalAddFromBuilder',rdata['id'])
        }
    } );	
        
        //~ $("#modalIsos #btn-hardware").on('click', function(e){
                //~ $('#modalIsos #hardware-block').show();
        //~ });
        	
}

function modal_add_isos_datatables(){
    modal_add_isos.destroy()
    $('#modalIsos #iso').val('');
    $('#modalIsos #datatables-error-status').empty()
    
    $('#modal_add_isos thead th').each( function () {
        var title = $(this).text();
        if(title=='Name'){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );
    
	modal_add_isos = $('#modal_add_isos').DataTable({
			"ajax": {
				"url": "/admin/table/isos/get",
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
				{ "data": "name"}
				],
			 "order": [[0, 'asc']],	
             "pageLength": 10,	 
	} );  

    modal_add_isos.columns().every( function () {
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
