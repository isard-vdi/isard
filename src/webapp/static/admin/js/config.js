/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {

    api.ajax('/admin/config/','POST',{}).done(function(data) {
        $.each( data, function( key, value ) {
            if(typeof(value) === "boolean"){
                $('#'+key).iCheck('disable');
                if(value){$('#'+key).iCheck('check');}
            }else{
                $('#'+key).val(value).prop('disabled',true);
            }
           
        });
    });  
    
    //~ Not using it now
    //~ show_disposables()
    
    $('.btn-edit').on( 'click', function () {
        basekey=$(this).attr('data-panel')
        api.ajax('/admin/config','POST',{}).done(function(data) {
            $.each( data, function( key, value ) {
                if(key.startsWith(basekey)){
                    if(typeof(value) === "boolean"){
                        $('#'+key).iCheck('enable');
                    }else{
                        $('#'+key).val(value).prop('disabled',false);
                    }
                }
            });
        });  
        $('.footer-'+basekey).css('display','block');
        $('[id^="btn-'+basekey+'-"]').show();
        //~ Not using it now
        //~ if(basekey=='disposable_desktops'){
            //~ activateDisposables();
        //~ }
            
    });

    $('.btn-cancel').on( 'click', function () {
        basekey=$(this).attr('data-panel')
        api.ajax('/admin/config','POST',{}).done(function(data) {
            $.each( data, function( key, value ) {
                if(key.startsWith(basekey)){
                    if(typeof(value) === "boolean"){
                        $('#'+key).iCheck('disable');
                    }else{
                        $('#'+key).val(value).prop('disabled',true);
                    }
                }
            });
        });  
        $('.footer-'+basekey).css('display','none');
        $('[id^="btn-'+basekey+'-"]').hide(); 
    });
    
    $('.btn-scheduler').on( 'click', function () {
        $('#modalScheduler').modal({
				backdrop: 'static',
				keyboard: false
        }).modal('show'); 
    });

    $("#modalScheduler #send").on('click', function(e){
            var form = $('#modalAddScheduler');
            data=$('#modalAddScheduler').serializeObject();
            socket.emit('scheduler_add',data)
            $("#modalAddScheduler")[0].reset();
            $("#modalAdd").modal('hide');
        });

	//~ Not using it now
    //~ $('.btn-add-disposables').on( 'click', function () {
        //~ $('#modalDisposable').modal({
				//~ backdrop: 'static',
				//~ keyboard: false
        //~ }).modal('show');
        //~ setTemplates()
    //~ });
        
    $('.btn-backup').on( 'click', function () {
				new PNotify({
						title: 'Create backup',
							text: "Do you really want to create a new backup?",
							hide: false,
							opacity: 0.9,
							confirm: {confirm: true},
							buttons: {closer: false,sticker: false},
							history: {history: false},
							addclass: 'pnotify-center'
						}).get().on('pnotify.confirm', function() {
                            api.ajax('/admin/backup','POST',{}).done(function(data) {
                            });  
						}).on('pnotify.cancel', function() {
				});	         
    });

    $('.btn-backups-upload').on( 'click', function () {
			$('#modalUpload').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');  
        });
        
    backups_table=$('#table-backups').DataTable({
			"ajax": {
				"url": "/admin/tabletest/backups/post",
                "contentType": "application/json",
                "type": 'POST',
                "data": function(d){return JSON.stringify({'order':'filename'})}
			},
            "sAjaxDataProp": "",
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
            "bLengthChange": false,
            "bFilter": false,
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{ "data": "when"},
				{ "data": "status"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "width": "88px",
                "defaultContent": '<button id="btn-backups-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-backups-restore" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-sign-in" style="color:darkgreen"></i></button> \
                                   <button id="btn-backups-info" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-info" style="color:green"></i></button> \
                                   <button id="btn-backups-download" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-download" style="color:darkblue"></i></button>'
				},
                ],
			 "order": [[0, 'desc']],
			 "columnDefs": [ {
							"targets": 0,
							"render": function ( data, type, full, meta ) {
                              if ( type === 'display' || type === 'filter' ) {
                                    return moment.unix(full.when).fromNow();
                              }                                 
                              return data;  
							}}]
    } );        
 
     $('#table-backups').find(' tbody').on( 'click', 'button', function () {
        var data = backups_table.row( $(this).parents('tr') ).data();
        if($(this).attr('id')=='btn-backups-delete'){
				new PNotify({
						title: 'Delete backup',
							text: "Do you really want to delete backup on date "+moment.unix(data.when).fromNow()+"?",
							hide: false,
							opacity: 0.9,
							confirm: {confirm: true},
							buttons: {closer: false,sticker: false},
							history: {history: false},
							addclass: 'pnotify-center'
						}).get().on('pnotify.confirm', function() {
                            api.ajax('/admin/backup_remove','POST',{'pk':data['id'],}).done(function(data) {
                            });  
						}).on('pnotify.cancel', function() {
				});	  
        }
        if($(this).attr('id')=='btn-backups-restore'){
				new PNotify({
						title: 'Restore backup',
							text: "Do you really want to restore backup from file "+data.filename+"?",
							hide: false,
							opacity: 0.9,
							confirm: {confirm: true},
							buttons: {closer: false,sticker: false},
							history: {history: false},
							addclass: 'pnotify-center'
						}).get().on('pnotify.confirm', function() {
                            api.ajax('/admin/restore','POST',{'pk':data['id'],}).done(function(data) {
                            });  
						}).on('pnotify.cancel', function() {
				});	  
        }
        if($(this).attr('id')=='btn-backups-download'){
						var url = '/admin/backup/download/'+data['id'];
						var anchor = document.createElement('a');
							anchor.setAttribute('href', url);
							anchor.setAttribute('download', data['filename']);
						var ev = document.createEvent("MouseEvents");
							ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
						anchor.dispatchEvent(ev);
        }
        if($(this).attr('id')=='btn-backups-info'){
						api.ajax('/admin/backup_info','POST',{'pk':data['id'],}).done(function(data) {
                            $("#backup-tables").find('option').remove();
                            $("#backup-tables").append('<option value="">Choose..</option>');
                            $.each(data.data,function(key, value) 
                            {
                                if(value>0){
                                    $("#backup-tables").append('<option value=' + key + '><strong>' + key+'</strong> ('+value+' items)' + '</option>');
                                }
                            });
                            $('#backup-id').val(data['id'])
                            $('#modalBackupInfo').modal({
                                backdrop: 'static',
                                keyboard: false
                            }).modal('show');  
                        });
        }        
    });                




    $('#backup-tables').on('change', function (e) {
			var valueSelected = this.value;
			api.ajax('/admin/backup_detailinfo','POST',{'pk':$('#backup-id').val(),'table':valueSelected}).done(function(data) {
				if ( $.fn.dataTable.isDataTable( '#backup-table-detail' ) ) {
					backup_table_detail.clear().rows.add(data).draw()
				}else{
				
					backup_table_detail=$('#backup-table-detail').DataTable( {
						data: data,
						rowId: 'id',
						//~ language: {
							//~ "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
						//~ },
						columns: [
							{ "data": "id", "width": "88px"},
							{ "data": "description", "width": "88px"},
							{
							"className":      'actions-control',
							"orderable":      false,
							"data":           null,
							"width": "88px",
							"defaultContent": '<button class="btn btn-xs btn-individual-restore" type="button"  data-placement="top"><i class="fa fa-sign-in" style="color:darkgreen"></i></button>'
							},
							],
						 "order": [[0, 'asc']],
						 "columnDefs": [ {
										"targets": 2,
										"render": function ( data, type, full, meta ) {
										  if(full.new_backup_data){
											  return '<button class="btn btn-xs btn-individual-restore" type="button"  data-placement="top"><i class="fa fa-sign-in" style="color:darkgreen"></i>New</button>';
										  }else{
											  return '<button class="btn btn-xs btn-individual-restore" type="button"  data-placement="top"><i class="fa fa-sign-in" style="color:darkgreen"></i>Exists</button>'
										  }
										}}]
					} );
				}
								$('.btn-individual-restore').on('click', function (e){
									data=backup_table_detail.row( $(this).parents('tr') ).data();
									table=$('#backup-tables').val()
									new PNotify({
											title: 'Restore data',
												text: "Do you really want to restore row "+data.id+" to table "+table+"?",
												hide: false,
												opacity: 0.9,
												confirm: {confirm: true},
												buttons: {closer: false,sticker: false},
												history: {history: false},
												addclass: 'pnotify-center'
											}).get().on('pnotify.confirm', function() {
												api.ajax('/admin/restore/'+table,'POST',{'data':data,}).done(function(data1) {
													api.ajax('/admin/backup_detailinfo','POST',{'pk':$('#backup-id').val(),'table':table}).done(function(data2) {
														data['new_backup_data']=false
														dtUpdateInsert(backup_table_detail,data,false);
													});
												});  
											}).on('pnotify.cancel', function() {
									});	                                                        
								}); 
								
                                // Api call to /admin/restore does not send correct data.
                                // New function should be done at AdminViews.py
								//~ $('.btn-bulk-restore').on('click', function(e) {
									//~ names=''
									//~ ids=[]
									//~ if(backup_table_detail.rows('.active').data().length){
										//~ $.each(backup_table_detail.rows('.active').data(),function(key, value){
											//~ names+=value['name']+'\n';
											//~ ids.push(value['id']);
										//~ });
										//~ var text = "You are about to restore these desktops:\n\n "+names
									//~ }else{ 
										//~ $.each(backup_table_detail.rows({filter: 'applied'}).data(),function(key, value){
											//~ ids.push(value['id']);
										//~ });
										//~ var text = "You are about to restore "+backup_table_detail.rows({filter: 'applied'}).data().length+". All the desktops in list!"
									//~ }
                                            //~ table=$('#backup-tables').val()
											//~ new PNotify({
													//~ title: 'Warning!',
														//~ text: text,
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
                                                        //~ api.ajax('/admin/restore/'+table,'POST',{'data':data,}).done(function(data1) {
                                                            //~ api.ajax('/admin/backup_detailinfo','POST',{'pk':$('#backup-id').val(),'table':table}).done(function(data2) {
                                                                //~ data['new_backup_data']=false
                                                                //~ dtUpdateInsert(backup_table_detail,data,false);
                                                            //~ });
                                                        //~ });                                                        
													//~ }).on('pnotify.cancel', function() {
											//~ });                                                        
									
								//~ });                                
				
				
			});
		});   
    
    scheduler_table=$('#table-scheduler').DataTable({
			"ajax": {
				"url": "/admin/table/scheduler_jobs/get",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
            "bLengthChange": false,
            "bFilter": false,
			"rowId": "id",
			"deferRender": true,
			"columns": [
                { "data": "name"},
				{ "data": "kind"},
				{ "data": "next_run_time"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "width": "58px",
                "defaultContent": '<button id="btn-scheduler-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button>'
				},
                ],
			 "order": [[1, 'asc']],
			 "columnDefs": [ {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
							  return moment.unix(full.next_run_time);
							}}]
    } );        
 
     $('#table-scheduler').find(' tbody').on( 'click', 'button', function () {
        var data = scheduler_table.row( $(this).parents('tr') ).data();
        if($(this).attr('id')=='btn-scheduler-delete'){
				new PNotify({
						title: 'Delete scheduled task',
							text: "Do you really want to delete scheduled task "+moment.unix(data.next_run_time)+"?",
							hide: false,
							opacity: 0.9,
							confirm: {confirm: true},
							buttons: {closer: false,sticker: false},
							history: {history: false},
							addclass: 'pnotify-center'
						}).get().on('pnotify.confirm', function() {
                            api.ajax('/admin/delete','POST',{'pk':data['id'],'table':'scheduler_jobs'}).done(function(data) {
                            });  
                            //~ api.ajax('/admin/delete','POST',{'pk':data['id'],'table':'scheduler_jobs'}).done(function(data) {
                            //~ });  
						}).on('pnotify.cancel', function() {
				});	  
        }
    }); 

    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_admins');

    socket.on('connect', function() {
        connection_done();
        console.log('Listening admins namespace');
        socket.emit('join_rooms',['config'])
        console.log('Listening config updates');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
    socket.on('user_quota', function(data) {
        console.log('Quota update')
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

    socket.on('backups_data', function(data){
        console.log('backup data received')
        var data = JSON.parse(data);
        dtUpdateInsert(backups_table,data,false);
    });
    
    socket.on('backups_deleted', function(data){
        console.log('backup deleted')
        var data = JSON.parse(data);
        var row = backups_table.row('#'+data.id).remove().draw();
        new PNotify({
                title: "Backup deleted",
                text: "Backup "+data.name+" has been deleted",
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
        });
    });

    socket.on('scheduler_jobs_data', function(data){
        console.log('sch data received')
        var data = JSON.parse(data);
        dtUpdateInsert(scheduler_table,data,false);
    });
    
    socket.on('scheduler_jobs_deleted', function(data){
        console.log('sch deleted')
        var data = JSON.parse(data);
        var row = scheduler_table.row('#'+data.id).remove().draw();
        new PNotify({
                title: "Scheduler deleted",
                text: "Scheduler "+data.name+" has been deleted",
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
        });
    });

    socket.on('disposables_deleted', function(data){
        console.log('disposable deleted')
        var data = JSON.parse(data);
        var row = disposables_table.row('#'+data.id).remove().draw();
        new PNotify({
                title: "Disposable deleted",
                text: "Disposable "+data.name+" has been deleted",
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
        });
    });

    socket.on('disposables_data', function(data){
        console.log('disposables data received')
        var data = JSON.parse(data);
        dtUpdateInsert(disposables_table,data,false);
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
            $("#modalAddScheduler")[0].reset();
            $("#modalScheduler").modal('hide');
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

});



//~ function show_disposables(){
        //~ // api.ajax('/admin/table/disposables/get','GET',{}).done(function(data) {
            //~ // $.each( data, function( key, value ) {
                //~ // disposables='';
                //~ // nets='';
                //~ // $.each( value['disposables'], function( k, v ) {
                    //~ // disposables=disposables+', '+v['name'];
                //~ // });
                //~ // $.each( value['nets'], function( k, v ) {
                    //~ // nets=nets+', '+v;
                //~ // });
                //~ // $("#table-disposables").append('<tr><td>'+value['name']+'</td><td>'+nets+'</td><td>'+disposables+'</td></tr>');
            //~ // });
        //~ // });

    //~ disposables_table=$('#table-disposables').DataTable({
			//~ "ajax": {
				//~ "url": "/admin/table/disposables/get",
				//~ "dataSrc": ""
			//~ },
			//~ "language": {
				//~ "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			//~ },
            //~ "bLengthChange": false,
            //~ "bFilter": false,
			//~ "rowId": "id",
			//~ "deferRender": true,
			//~ "columns": [
				//~ { "data": "name"},
				//~ { "data": "nets[, ]"},
                //~ { "data": "disposables"},
				//~ {
                //~ "className":      'actions-control',
                //~ "orderable":      false,
                //~ "data":           null,
                //~ "width": "58px",
                //~ "defaultContent": '<button id="btn-disposable_desktops-delete" class="btn btn-xs" type="button"  data-placement="top" style="display:none"><i class="fa fa-times" style="color:darkred"></i></button>'
                                   //~ // <button id="btn-disposable_desktops-edit" class="btn btn-xs" type="button"  data-placement="top" style="display:none"><i class="fa fa-pencil" style="color:darkblue"></i></button>'
				//~ },
                //~ ],
			 //~ "order": [[1, 'asc']],
			 //~ "columnDefs": [ {
							//~ "targets": 2,
							//~ "render": function ( data, type, full, meta ) {
							  //~ return renderDisposables(full);
							//~ }}]
    //~ } );        

     //~ $('#table-disposables').find(' tbody').on( 'click', 'button', function () {
        //~ var data = disposables_table.row( $(this).parents('tr') ).data();
        //~ if($(this).attr('id')=='btn-disposable_desktops-delete'){
				//~ new PNotify({
						//~ title: 'Delete disposable',
							//~ text: "Do you really want to delete disposable "+ data.name+"?",
							//~ hide: false,
							//~ opacity: 0.9,
							//~ confirm: {confirm: true},
							//~ buttons: {closer: false,sticker: false},
							//~ history: {history: false},
							//~ addclass: 'pnotify-center'
						//~ }).get().on('pnotify.confirm', function() {
                            //~ api.ajax('/admin/delete','POST',{'pk':data['id'],'table':'disposables'}).done(function(data) {
                            //~ });  
						//~ }).on('pnotify.cancel', function() {
				//~ });	  
        //~ }
        //~ if($(this).attr('id')=='btn-disposable_desktops-edit'){
			//~ $('#modalDisposable').modal({
				//~ backdrop: 'static',
				//~ keyboard: false
			//~ }).modal('show');   
            //~ // $("#select2-disposables").select2Sortable();         
        //~ }
    //~ });
 
//~ }

//~ function renderDisposables(data){
      //~ var return_data = new Array();
      //~ for(var i=0;i< data['disposables'].length; i++){
        //~ return_data.push(data['disposables'][i].name)
      //~ }
      //~ return return_data;
//~ }


//~ function setTemplates(){

			 //~ $('#disposables').select2({
				//~ minimumInputLength: 2,
				//~ multiple: true,
				//~ ajax: {
					//~ type: "POST",
					//~ url: '/admin/getAllTemplates',
					//~ dataType: 'json',
					//~ contentType: "application/json",
					//~ delay: 250,
					//~ data: function (params) {
						//~ return  JSON.stringify({
							//~ term: params.term,
							//~ pluck: ['id','name']
						//~ });
					//~ },
					//~ processResults: function (data) {
						//~ return {
							//~ results: $.map(data, function (item, i) {
								//~ return {
									//~ text: item.name,
									//~ id: item.id
								//~ }
							//~ })
						//~ };
					//~ }
				//~ },
			//~ });	
//~ };

