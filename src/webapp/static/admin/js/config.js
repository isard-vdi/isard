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
    show_disposables()
    
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
        if(basekey=='disposable_desktops'){
            activateDisposables();
        }
            
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

    //~ $('#btn-checkport').on( 'click', function (event) {
        //~ event.preventDefault()
					//~ api.ajax('/admin/config/checkport','POST',{'pk':data['id'],'server':$('#engine-grafana-server').value,'port':$('#engine-grafana-web_port').value}).done(function(data) {
                        //~ console.log(data);
                    //~ });  
    //~ });
    
    //~ function checkPort(){
					//~ api.ajax('/admin/config/checkport','POST',{'pk':data['id'],'server':$('#engine-grafana-server').value,'port':$('#engine-grafana-web_port').value}).done(function(data) {
                        //~ console.log(data);
                    //~ });          
    //~ }
    
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
            //~ form.parsley().validate();

            //~ if (form.parsley().isValid()){
                //~ template=$('#modalAddDesktop #template').val();
                //~ console.log('TEMPLATE:'+template)
                //~ if (template !=''){
                    //~ data=$('#modalAdd').serializeObject();
                    //~ console.log(data)
                    //~ socket.emit('domain_add',data)
                //~ }else{
                    //~ $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    //~ $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                //~ }
            //~ }
        });


    $('.btn-add-disposables').on( 'click', function () {
        $('#modalDisposable').modal({
				backdrop: 'static',
				keyboard: false
        }).modal('show');
        setTemplates()
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
							stack: stack_center
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
							stack: stack_center
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
							stack: stack_center
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
                                $("#backup-tables").append('<option value=' + key + '>' + key+'('+value+')' + '</option>');
                            });
                            $('#backup-id').val(data['id'])
                            $('#modalBackupInfo').modal({
                                backdrop: 'static',
                                keyboard: false
                            }).modal('show');  
                         
                            //~ new PNotify({
                                    //~ title: 'Delete backup',
                                        //~ text: objToString(data.db),
                                        //~ hide: false,
                                        //~ opacity: 1,
                                        //~ confirm: {confirm: true},
                                        //~ buttons: {closer: false,sticker: false},
                                        //~ history: {history: false},
                                        //~ stack: stack_center
                                    //~ }).get().on('pnotify.confirm', function() {
                                    //~ }).on('pnotify.cancel', function() {
                            //~ });	
                            });
        }        
    });                




                            //~ backup_table_detail=''
    $('#backup-tables').on('change', function (e) {
                                //~ var optionSelected = $("option:selected", this);
                                //~ console.log(optionSelected)
                                var valueSelected = this.value;
                                //~ console.log(valueSelected+' '+$('#backup-id').val())
                                api.ajax('/admin/backup_detailinfo','POST',{'pk':$('#backup-id').val(),'table':valueSelected}).done(function(data) {
                                    //~ console.log($('#backup-id').val())
                                    //~ console.log(data)
                                    //~ columns=[];
                                    //~ $.each(data[0],function(key, value) 
                                    //~ {
                                        //~ if(key == 'id'){
                                            //~ columns.push({'data':key})
                                        //~ }
                                    //~ });
                                    //~ backup_table_detail.destroy()
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
                                                        //~ table=$('#backup-id').val()
                                                        new PNotify({
                                                                title: 'Restore data',
                                                                    text: "Do you really want to restore row "+data.id+" to table "+table+"?",
                                                                    hide: false,
                                                                    opacity: 0.9,
                                                                    confirm: {confirm: true},
                                                                    buttons: {closer: false,sticker: false},
                                                                    history: {history: false},
                                                                    stack: stack_center
                                                                }).get().on('pnotify.confirm', function() {
                                                                    api.ajax('/admin/restore/'+table,'POST',{'data':data,}).done(function(data1) {
                                                                        api.ajax('/admin/backup_detailinfo','POST',{'pk':$('#backup-id').val(),'table':table}).done(function(data2) {
                                                                            data['new_backup_data']=false
                                                                            dtUpdateInsert(backup_table_detail,data,false);
                                                                            //~ setDomainDetailButtonsStatus(data.id, data.status);
                                                                            //~ backup_table_detail.clear().rows.add(data2).draw()
                                                                        });
                                                                    });  
                                                                }).on('pnotify.cancel', function() {
                                                        });	                                                        
                                                    }); 
                                                    
                                                    $('.btn-bulk-restore').on('click', function(e) {
                                                        names=''
                                                        ids=[]
                                                        if(backup_table_detail.rows('.active').data().length){
                                                            $.each(backup_table_detail.rows('.active').data(),function(key, value){
                                                                names+=value['name']+'\n';
                                                                ids.push(value['id']);
                                                            });
                                                            var text = "You are about to restore these desktops:\n\n "+names
                                                        }else{ 
                                                            $.each(backup_table_detail.rows({filter: 'applied'}).data(),function(key, value){
                                                                ids.push(value['id']);
                                                            });
                                                            var text = "You are about to restore "+backup_table_detail.rows({filter: 'applied'}).data().length+". All the desktops in list!"
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
                                                                            //~ api.ajax('/admin/mdomains','POST',{'ids':ids,'action':action}).done(function(data) {
                                                                                //~ $('#mactions option[value="none"]').prop("selected",true);
                                                                            //~ }); 
                                                                        }).on('pnotify.cancel', function() {
                                                                            //~ $('#mactions option[value="none"]').prop("selected",true);
                                                                });                                                        
                                                        
                                                    });                                
                                    
                                    
                                });
                            });   



    //~ // Stream backups_source
	//~ if (!!window.EventSource) {
	  //~ var backups_source = new EventSource('/admin/stream/backups');
      //~ console.log('Listening backups...');
	//~ } else {
	  // Result to xhr polling :(
	//~ }

	//~ window.onbeforeunload = function(){
	  //~ backups_source.close();
	//~ };

	//~ backups_source.addEventListener('open', function(e) {
	  //~ // Connection was opened.
	//~ }, false);

	//~ backups_source.addEventListener('error', function(e) {
	  //~ if (e.readyState == EventSource.CLOSED) {
		//~ // Connection was closed.
	  //~ }
     
	//~ }, false);

	//~ backups_source.addEventListener('New', function(e) {
	  //~ var data = JSON.parse(e.data);
		//~ if($("#" + data.id).length == 0) {
		  //~ //it doesn't exist
		  //~ backups_table.row.add(data).draw();
            //~ new PNotify({
                //~ title: "Backup added",
                //~ text: "Backups "+data.filename+" has been created",
                //~ hide: true,
                //~ delay: 2000,
                //~ icon: 'fa fa-success',
                //~ opacity: 1,
                //~ type: 'success'
            //~ });          
		//~ }else{
          //~ //if already exists do an update (ie. connection lost and reconnect)
          //~ var row = table.row('#'+data.id); 
          //~ backups_table.row(row).data(data);			
		//~ }
	//~ }, false);

	//~ backups_source.addEventListener('Status', function(e) {
          //~ var data = JSON.parse(e.data);
          //~ var row = backups_table.row('#'+data.id); 
          //~ backups_table.row(row).data(data);
	//~ }, false);

	//~ backups_source.addEventListener('Deleted', function(e) {
	  //~ var data = JSON.parse(e.data);
      //~ var row = backups_table.row('#'+data.id).remove().draw();
            //~ new PNotify({
                //~ title: "Backup deleted",
                //~ text: "Backup "+data.name+" has been deleted",
                //~ hide: true,
                //~ delay: 2000,
                //~ icon: 'fa fa-success',
                //~ opacity: 1,
                //~ type: 'info'
            //~ });
	//~ }, false);


    
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
							stack: stack_center
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
		//~ if($("#" + data.id).length == 0) {
		  //~ //it doesn't exist
		  //~ backups_table.row.add(data).draw();
		//~ }else{
          //~ //if already exists do an update (ie. connection lost and reconnect)
          //~ var row = backups_table.row('#'+data.id); 
          //~ backups_table.row(row).data(data).invalidate();			
		//~ }
        //~ backups_table.draw(false);
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

    //~ // Stream scheduler_source
	//~ if (!!window.EventSource) {
	  //~ var scheduler_source = new EventSource('/admin/stream/scheduler_jobs');
      //~ console.log('Listening scheduler...');
	//~ } else {
	  // Result to xhr polling :(
	//~ }

	//~ window.onbeforeunload = function(){
	  //~ scheduler_source.close();
	//~ };

	//~ scheduler_source.addEventListener('open', function(e) {
	  //~ // Connection was opened.
	//~ }, false);

	//~ scheduler_source.addEventListener('error', function(e) {
	  //~ if (e.readyState == EventSource.CLOSED) {
		//~ // Connection was closed.
	  //~ }
     
	//~ }, false);

	//~ scheduler_source.addEventListener('New', function(e) {
	  //~ var data = JSON.parse(e.data);
		//~ if($("#" + data.id).length == 0) {
		  //~ //it doesn't exist
		  //~ scheduler_table.row.add(data).draw();
            //~ new PNotify({
                //~ title: "Scheduler added",
                //~ text: "Scheduler "+data.name+" has been created",
                //~ hide: true,
                //~ delay: 2000,
                //~ icon: 'fa fa-success',
                //~ opacity: 1,
                //~ type: 'success'
            //~ });          
		//~ }else{
          //~ //if already exists do an update (ie. connection lost and reconnect)
          //~ var row = table.row('#'+data.id); 
          //~ scheduler_table.row(row).data(data);			
		//~ }
	//~ }, false);

	//~ scheduler_source.addEventListener('Deleted', function(e) {
	  //~ var data = JSON.parse(e.data);
      //~ var row = scheduler_table.row('#'+data.id).remove().draw();
            //~ new PNotify({
                //~ title: "Scheduler deleted",
                //~ text: "Scheduler "+data.name+" has been deleted",
                //~ hide: true,
                //~ delay: 2000,
                //~ icon: 'fa fa-success',
                //~ opacity: 1,
                //~ type: 'info'
            //~ });
	//~ }, false);

});



function show_disposables(){
        //~ api.ajax('/admin/table/disposables/get','GET',{}).done(function(data) {
            //~ $.each( data, function( key, value ) {
                //~ disposables='';
                //~ nets='';
                //~ $.each( value['disposables'], function( k, v ) {
                    //~ disposables=disposables+', '+v['name'];
                //~ });
                //~ $.each( value['nets'], function( k, v ) {
                    //~ nets=nets+', '+v;
                //~ });
                //~ $("#table-disposables").append('<tr><td>'+value['name']+'</td><td>'+nets+'</td><td>'+disposables+'</td></tr>');
            //~ });
        //~ });

    disposables_table=$('#table-disposables').DataTable({
			"ajax": {
				"url": "/admin/table/disposables/get",
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
				{ "data": "nets[, ]"},
                { "data": "disposables"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "width": "58px",
                "defaultContent": '<button id="btn-disposable_desktops-delete" class="btn btn-xs" type="button"  data-placement="top" style="display:none"><i class="fa fa-times" style="color:darkred"></i></button>'
                                   //~ <button id="btn-disposable_desktops-edit" class="btn btn-xs" type="button"  data-placement="top" style="display:none"><i class="fa fa-pencil" style="color:darkblue"></i></button>'
				},
                ],
			 "order": [[1, 'asc']],
			 "columnDefs": [ {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
							  return renderDisposables(full);
							}}]
    } );        

     $('#table-disposables').find(' tbody').on( 'click', 'button', function () {
        var data = disposables_table.row( $(this).parents('tr') ).data();
        if($(this).attr('id')=='btn-disposable_desktops-delete'){
				new PNotify({
						title: 'Delete disposable',
							text: "Do you really want to delete disposable "+ data.name+"?",
							hide: false,
							opacity: 0.9,
							confirm: {confirm: true},
							buttons: {closer: false,sticker: false},
							history: {history: false},
							stack: stack_center
						}).get().on('pnotify.confirm', function() {
                            api.ajax('/admin/delete','POST',{'pk':data['id'],'table':'disposables'}).done(function(data) {
                            });  
						}).on('pnotify.cancel', function() {
				});	  
        }
        if($(this).attr('id')=='btn-disposable_desktops-edit'){
			$('#modalDisposable').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');   
            //~ $("#select2-disposables").select2Sortable();         
        }
    });
 
}

function renderDisposables(data){
      var return_data = new Array();
      for(var i=0;i< data['disposables'].length; i++){
        return_data.push(data['disposables'][i].name)
      }
      return return_data;
}

function activateDisposables(){
       
}

function setTemplates(){

			 $('#disposables').select2({
				minimumInputLength: 2,
				multiple: true,
				ajax: {
					type: "POST",
					url: '/admin/getAllTemplates',
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
									text: item.name,
									id: item.id
								}
							})
						};
					}
				},
			});	
};

	//~ modal_add_desktops = $('#modal_add_desktops').DataTable({
			//~ "ajax": {
				//~ "url": "/desktops/getAllTemplates",
				//~ "dataSrc": ""
			//~ },

            //~ "scrollY":        "125px",
            //~ "scrollCollapse": true,
            //~ "paging":         false,
            
            //"searching":         false,
			//~ "language": {
				//~ "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                //~ "zeroRecords":    "No matching templates found",
                //~ "info":           "Showing _START_ to _END_ of _TOTAL_ templates",
                //~ "infoEmpty":      "Showing 0 to 0 of 0 templates",
                //~ "infoFiltered":   "(filtered from _MAX_ total templates)"
			//~ },
			//~ "rowId": "id",
			//~ "deferRender": true,
			//~ "columns": [
                //~ { "data": "kind", "width": "10px", "orderable": false},
				//~ { "data": "name"},
                //~ { "data": "group", "width": "10px"},
                //~ { "data": "username"}
				//~ ],
			 //~ "order": [[0, 'asc']],	
             //~ "pageLength": 5,	 
		//~ "columnDefs": [     
                            //~ {
							//~ "targets": 0,
							//~ "render": function ( data, type, full, meta ) {
							  //~ return renderTemplateKind(full);
							//~ }},
							//~ {
							//~ "targets": 1,
							//~ "render": function ( data, type, full, meta ) {
							  //~ return renderIcon1x(full)+" "+full.name;
							//~ }},
							//~ ]



	//~ } );  
    
