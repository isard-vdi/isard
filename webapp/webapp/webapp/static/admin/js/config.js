/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {
    $('.btn-scheduler').on( 'click', function () {
        $('#modalScheduler').modal({
				backdrop: 'static',
				keyboard: false
        }).modal('show'); 
    });

    $("#modalScheduler #send").on('click', function(e){
            var form = $('#modalAddScheduler');
            data=$('#modalAddScheduler').serializeObject();
            api.ajax('/scheduler/system/'+data["kind"]+"/"+data["action"]+"/"+data["hour"]+"/"+data["minute"],'POST',{}).done(function(data) {
            });
            $("#modalAddScheduler")[0].reset();
            $("#modalScheduler").modal('hide');
        });

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
                            api.ajax('/api/v3/backup','POST',{}).done(function(data) {
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
				"url": "/api/v3/admin/table/backups",
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
                { "data": "version", "defaultContent": "Unknown"},
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
                            api.ajax('/api/v3/backup/'+data["id"],'DELETE',{}).done(function(data) {
                            });  
						}).on('pnotify.cancel', function() {
				});	  
        }
        if($(this).attr('id')=='btn-backups-restore'){
				new PNotify({
						title: 'Restore backup',
							text: "Do you really want to restore backup from file "+data.filename+"? NOTE: After restoring isard-engine container MUST be restarted to apply db version upgrade!",
							hide: false,
							opacity: 0.9,
							confirm: {confirm: true},
							buttons: {closer: false,sticker: false},
							history: {history: false},
							addclass: 'pnotify-center'
						}).get().on('pnotify.confirm', function() {
                            api.ajax('/api/v3/backup/restore/'+data["id"],'PUT',{}).done(function(data) {
                            });  
						}).on('pnotify.cancel', function() {
				});	  
        }
        if($(this).attr('id')=='btn-backups-download'){
						var url = '/api/v3/backup/download/'+data['id']+'?jwt='+localStorage.getItem("token");
						var anchor = document.createElement('a');
							anchor.setAttribute('href', url);
							anchor.setAttribute('download', data['filename']);
						var ev = document.createEvent("MouseEvents");
							ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
						anchor.dispatchEvent(ev);
        }
        if($(this).attr('id')=='btn-backups-info'){
						api.ajax('/api/v3/backup/'+data["id"],'GET',{}).done(function(data) {
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
            // var backup_id = +'/'+$('#backup-id').val()
			api.ajax('/api/v3/backup/table/'+valueSelected,'GET',{}).done(function(data) {
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
							{ "data": "description", "width": "88px", "defaultContent": ""},
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
												api.ajax('/api/v3/backup/restore/table/'+table,'PUT',{'data':data,}).done(function(data1) {
													api.ajax('/api/v3/backup/table/'+table,'GET',{}).done(function(data) {
														dtUpdateInsert(backup_table_detail,data,false);
													});
												});  
											}).on('pnotify.cancel', function() {
									});	                                                        
								}); 
			});
		});   
    
    
        scheduler_table=$('#table-scheduler').DataTable({
            "ajax": {
                "url": "/admin/table/scheduler_jobs",
                "data": function(d){return JSON.stringify({'order_by':'date','pluck':['id','name','kind','next_run_time'],'id':'system','index':'type'})},
                "contentType": "application/json",
                "type": 'POST',
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
                            api.ajax('/scheduler/'+data["id"],'DELETE',{}).done(function(data) {
                                // Websocket event will delete it
                                // scheduler_table.row('#'+data["id"]).remove().draw();
                            });   
						}).on('pnotify.cancel', function() {
				});	  
        }
    }); 

    maintenance_update_checkbox = (enabled) => {
        let status
        if (enabled) {
            status = 'check'
        } else {
            status = 'uncheck'
        }
        $('#maintenance_checkbox').iCheck(status)
    }
    maintenance_bind_checkbox = () => {
        $('#maintenance_checkbox').on('ifChecked', () => {
            maintenance_update_status(true)
        })
        $('#maintenance_checkbox').on('ifUnchecked', () => {
            maintenance_update_status(false)
        })
    }
    maintenance_update_status = (enabled) => {
        $('#maintenance_wrapper').hide()
        $('#maintenance_spinner').show()
        $('#maintenance_checkbox').unbind('ifChecked')
        $('#maintenance_checkbox').unbind('ifUnchecked')
        api.ajax(
            '/api/v3/maintenance',
            'PUT',
            enabled
        ).done((data) => {
            maintenance_update_checkbox(data)
            maintenance_bind_checkbox()
            $('#maintenance_spinner').hide()
            $('#maintenance_wrapper').show()
        })
    }
    api.ajax('/api/v3/maintenance', 'GET').done((data) => {
        maintenance_update_checkbox(data)
        maintenance_bind_checkbox()
        $('#maintenance_spinner').hide()
        $('#maintenance_wrapper').show()
    })

    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/administrators', {
        'query': {'jwt': localStorage.getItem("token")},
        'path': '/api/v3/socket.io/',
        'transports': ['websocket']
    });

    socket.on('connect', function() {
        connection_done();
        console.log('Listening admins namespace');
        console.log('Listening config updates');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
    socket.on('user_quota', function(data) {
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

    socket.on('backups_data', function(data){
        var data = JSON.parse(data);
        dtUpdateInsert(backups_table,data,false);
    });
    
    socket.on('backups_deleted', function(data){
        var data = JSON.parse(data);
        backups_table.row('#'+data.id).remove().draw();
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
        var data = JSON.parse(data);
        dtUpdateInsert(scheduler_table,data,false);
    });
    
    socket.on('scheduler_jobs_deleted', function(data){
        var data = JSON.parse(data);
        scheduler_table.row('#'+data.id).remove().draw();
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
