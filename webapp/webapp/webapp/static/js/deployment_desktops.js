/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


columns= [

]

$(document).ready(function() {

    $template_domain = $(".template-detail-domain");
    $('#mactions option[value="none"]').prop("selected",true);

    $('#domains tfoot th').each( function () {
        var title = $(this).text();
        if (['','Icon','Hypervisor','Action'].indexOf(title) == -1){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );

    table= $('#domains').DataTable({
        "ajax": {
            "url": "/isard-admin/desktops/tagged",
            "dataSrc": ""
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "deferRender": true,
        "columns": [    {
            "className":      'details-control',
            "orderable":      false,
            "data":           null,
            "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "icon" },
            { "data": "tag", "width": "100px"},
            { "data": "name"},
            { "data": null},
            { "data": "status"},
            { "data": "kind"},
            { "data": "username"},
            { "data": "category"},
            { "data": "group"},
            { "data": "accessed",
             'defaultContent': ''}],
         "order": [[4, 'asc']],
         "columnDefs": [ {
                        "targets": 1,
                        "render": function ( data, type, full, meta ) {
                          return renderIcon(full);
                        }},
                        {
                        "targets": 2,
                        "render": function ( data, type, full, meta ) {
                            return full.tag.split('_')[2];
                            if(type === 'display'){
                                
                            }else{
                                return full
                            }
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
                        }}
                        ],
                        "initComplete" :
                            function () {
                                this.api().columns(2).every( function () {
                                var column = this;
                                $('#dataTables-example .head .head_hide').html('');
                        
                                var select = $('<select id="formfilter" class="filterdropdown"><option value="">'+$(column.header()).text()+'</option></select>')
                                    .appendTo( $(column.header()).empty())
                                    .on( 'change', function () {
                                        var val = $.fn.dataTable.util.escapeRegex(
                                            $(this).val()
                                        );
                                        column
                                            .search( val ? '^'+val+'$' : '', true, false )
                                            .draw();
                                    });
                        
                                column.data().unique().sort().each( function ( d, j ) {
                                    select.append( '<option value="'+d.split('_')[2]+'">'+d.split('_')[2]+'</option>' )
                                });
                            });
                        }
  

       
    } );

    table.columns().every( function () {
        var that = this;
 
        $( 'input', this.footer() ).on( 'keyup change', function () {
            if ( that.search() !== this.value ) {
                that
                    .search( this.value )
                    .draw();
            }
        } );
    } );

    table.on( 'click', 'tr', function () {
        $(this).toggleClass('active');
    } );

    $('#mactions').on('change', function () {
        action=$(this).val();
        names=''
        ids=[]
        deployments=[]
        if(table.rows('.active').data().length){
            $.each(table.rows('.active').data(),function(key, value){
                names+=value['name']+'\n';
                ids.push(value['id']);
                deployments.push(value['tag'])
            });
            var text = "You are about to "+action+" these desktops:\n\n "+names
        }else{ 
            $.each(table.rows({filter: 'applied'}).data(),function(key, value){
                ids.push(value['id']);
                deployments.push(value['tag'])
            });
            var text = "You are about to "+action+" "+table.rows({filter: 'applied'}).data().length+" desktops!\n All the desktops in list!"
        }

        if(ids.length != deployments.length){
            new PNotify({
                title: "Deployment actions error!",
                    text: "Desktop in action without tag",
                    hide: true,
                    delay: 3000,
                    icon: 'fa fa-alert-sign',
                    opacity: 1,
                    type: 'error'
                });
        }else{
            text=text+', from this deployments:\n'
            unique_deployments = deployments.filter(onlyUnique)
            $.each(unique_deployments,function(key,value){
                text=text+value.split("_").slice(-1)[0]+'\n'
            });
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
                    console.log('mactions')
                    api.ajax('/isard-admin/advanced/mdomains','POST',{'ids':ids,'action':action}).done(function(data) {
                        $('#mactions option[value="none"]').prop("selected",true);
                    }); 
                }).on('pnotify.cancel', function() {
                    $('#mactions option[value="none"]').prop("selected",true);
                });
            }
    } );
    
    $('#domains').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = table.row( tr );
 
        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
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
                row.child( addDomainDetailPannel(row.data()) ).show();
                tr.addClass('shown');
                $('#status-detail-'+row.data().id).html(row.data().detail);
                actionsDomainDetail();
                setDomainDetailButtonsStatus(row.data().id,row.data().status)
                //if(row.data().status=='Stopped' || row.data().status=='Started' || row.data().status=='Failed'){
                    //~ setDomainGenealogy(row.data().id);
                    setDomainHotplug(row.data().id, row.data());
                    setHardwareDomainDefaults_viewer('#hardware-'+row.data().id,row.data());
                        setAlloweds_viewer('#alloweds-'+row.data().id,row.data().id);
                        //~ setDomainDerivates(row.data().id);

                //}
            }            
        }
    } );	


	// DataTable buttons
    $('#domains tbody').on( 'click', 'button', function () {
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
                setViewerButtons(data['id'],socket);

                $('#modalOpenViewer').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');           

                break;
            case 'btn-alloweds':
                modalAllowedsFormShow('domains',data)
                break;                 
        }
    });	

    modal_add_desktops = $('#modal_add_desktops').DataTable()
    initalize_modal_all_desktops_events()
    $("#modalAddDesktop #send-block").unbind('click');
    $('.btn-add-desktop').on('click', function () {
        $('#allowed-title').html('')
        $('#alloweds_panel').css('display','block');
        setAlloweds_add('#alloweds-block');
        if ($('meta[id=user_data]').attr('data-role') == 'advanced'){
            $('#categories_pannel').hide();
            $('#roles_pannel').hide();
        }

        $("#modalAddDesktop #send-block").on('click', function(e){
            var form = $('#modalAdd');

            form.parsley().validate();
    
            if (form.parsley().isValid()){
                template=$('#modalAddDesktop #template').val();
                if (template !=''){
                    data=$('#modalAdd').serializeObject();
                    data=replaceAlloweds_arrays('#modalAddDesktop #alloweds-block',data)
                    console.log(data)
                    socket.emit('domain_add_advanced',data)
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

    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/isard-admin/sio_users');

    socket.on('connect', function() {
        connection_done();
        socket.emit('join_rooms',['tagged'])
        console.log('Listening tags namespace');
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
        if(data.status =='Started' && table.row('#'+data.id).data().status != 'Started'){
            // if('preferred' in data['options']['viewers'] && data['options']['viewers']['preferred']){
            //     socket.emit('domain_viewer',{'pk':data.id,'kind':data['options']['viewers']['preferred'],'os':getOS()});
            // }else{
            //      setViewerButtons(data.id,socket);
            //         $('#modalOpenViewer').modal({
            //             backdrop: 'static',
            //             keyboard: false
            //         }).modal('show');
            // }
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

function addDomainDetailPannel ( d ) {
    $newPanel = $template_domain.clone();
        $newPanel = $template_domain.clone();
        $newPanel.find('#derivates-d\\.id').remove();

    $newPanel.html(function(i, oldHtml){
        return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name);
    });
    return $newPanel
}

function setDomainDetailButtonsStatus(id,status){
    if(status=='Started' || status=='Starting'){
        $('#actions-'+id+' *[class^="btn"]').prop('disabled', true);
        $('#actions-'+id+' .btn-jumperurl').prop('disabled', false);           
    }else{
        $('#actions-'+id+' *[class^="btn"]').prop('disabled', false);
    }
}

function setDesktopDetailButtonsStatus(id,status){
    
    if(status=='Stopped'){
        $('#actions-'+id+' *[class^="btn"]').prop('disabled', false);
    }else{
        $('#actions-'+id+' *[class^="btn"]').prop('disabled', true);
        $('#actions-'+id+' .btn-jumperurl').prop('disabled', false);
    }
    if(status=='Failed'){
      $('#actions-'+id+' .btn-edit').prop('disabled', false);
      $('#actions-'+id+' .btn-delete').prop('disabled', false);
    }
}

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
        api.ajax('/isard-admin/admin/domains/jumperurl/'+pk,'GET',{}).done(function(data) {
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
            
            api.ajax('/isard-admin/admin/domains/jumperurl_reset/'+pk,'GET',{}).done(function(data) {
                $('#jumperurl').val(location.protocol + '//' + location.host+'/vw/'+data);
            });         
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
                api.ajax('/isard-admin/admin/domains/jumperurl_disable/'+pk,'GET',{}).done(function(data) {
                    $('#jumperurl').val('');
                }); 
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
        api.ajax('/isard-admin/admin/load/domains/post','POST',{'id':pk,'pluck':['id','forced_hyp']}).done(function(data) {        
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
            api.ajax('/isard-admin/admin/load/domains/post','POST',{'id':pk,'pluck':['id','forced_hyp']}).done(function(data) {        
                
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
        $("#modalForcedhypForm #forced_hyp").empty()
    }); 

    $("#modalForcedhyp #send").on('click', function(e){
        data=$('#modalForcedhypForm').serializeObject();
        if('forced_hyp' in data){
            socket.emit('forcedhyp_update',{'id':data.id,'forced_hyp':[data.forced_hyp]})
        }else{
            socket.emit('forcedhyp_update',{'id':data.id,'forced_hyp':false})
        }
    });
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

function renderIcon(data){
    return '<span class="xe-icon" data-pk="'+data.id+'">'+icon(data)+'</span>'
}

function renderStatus(data){
    return data.status;
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
    if(status=='Crashed'){
        return '<div class="Change"> <i class="fa fa-thumbs-o-down fa-2x"></i> </div>';
    } 
    if(status=='Stopped' || status=='Failed'){
            return '<button type="button" id="btn-play" class="btn btn-pill-right btn-success btn-xs"><i class="fa fa-play"></i> Start</button>';
    }
    if(status=='Started'){
            return '<button type="button" id="btn-stop" class="btn btn-pill-left btn-danger btn-xs"><i class="fa fa-stop"></i> Stop</button>';
    } 

    if(status=='Disabled' || status =='Manteinance'){
            return '<i class="fa fa-times fa-2x"></i>';
    }         
    return '<i class="fa fa-spinner fa-pulse fa-2x fa-fw"></i>';        
}	

function renderDisplay(data){
    if(data.status=='Stopping' || data.status =='Started'){
        return '<button type="button" id="btn-display" class="btn btn-pill-right btn-success btn-xs"> \
                <i class="fa fa-desktop"></i> Show</button>';
    }
    return ''
}

function onlyUnique(value, index, self) {
    return self.indexOf(value) === index;
  }