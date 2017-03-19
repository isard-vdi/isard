/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {


    api.ajax('/admin/config','POST',{}).done(function(data) {
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

    $('#btn-checkport').on( 'click', function (event) {
        event.preventDefault()
                    console.log($('#engine-carbon-server').value)
					api.ajax('/admin/config/checkport','POST',{'pk':data['id'],'server':$('#engine-carbon-server').value,'port':$('#engine-carbon-port').value}).done(function(data) {
                        console.log(data);
                    });  
    });
    
    function checkPort(){
					api.ajax('/admin/config/checkport','POST',{'pk':data['id'],'server':$('#engine-carbon-server').value,'port':$('#engine-carbon-port').value}).done(function(data) {
                        console.log(data);
                    });          
    }
    
    $('.btn-scheduler').on( 'click', function () {
        $('#modalScheduler').modal({
				backdrop: 'static',
				keyboard: false
        }).modal('show'); 
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
    
    backups_table=$('#table-backups').DataTable({
			"ajax": {
				"url": "/admin/table/backups/get",
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
				{ "data": "when"},
				{ "data": "status"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "width": "58px",
                "defaultContent": '<button id="btn-backups-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-backups-restore" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-sign-in" style="color:darkblue"></i></button>'
				},
                ],
			 "order": [[1, 'asc']],
			 "columnDefs": [ {
							"targets": 0,
							"render": function ( data, type, full, meta ) {
							  return moment.unix(full.when).fromNow();
							}}]
    } );        
 
     $('#table-backups').find(' tbody').on( 'click', 'button', function () {
        var data = backups_table.row( $(this).parents('tr') ).data();
        console.log($(this).attr('id'),data);
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
                "defaultContent": '<button id="btn-scheduler-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-scheduler-restore" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-sign-in" style="color:darkblue"></i></button>'
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
        console.log($(this).attr('id'),data);
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
    });           


    // Stream domains_source
	if (!!window.EventSource) {
	  var backups_source = new EventSource('/admin/stream/backups');
      console.log('Listening backups...');
	} else {
	  //~ // Result to xhr polling :(
	}

	window.onbeforeunload = function(){
	  backups_source.close();
	};

	backups_source.addEventListener('open', function(e) {
	  // Connection was opened.
	}, false);

	backups_source.addEventListener('error', function(e) {
	  if (e.readyState == EventSource.CLOSED) {
		// Connection was closed.
	  }
     
	}, false);

	backups_source.addEventListener('New', function(e) {
	  var data = JSON.parse(e.data);
		if($("#" + data.id).length == 0) {
		  //it doesn't exist
		  backups_table.row.add(data).draw();
            new PNotify({
                title: "Backup added",
                text: "Backups "+data.filename+" has been created",
                hide: true,
                delay: 2000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
            });          
		}else{
          //if already exists do an update (ie. connection lost and reconnect)
          var row = table.row('#'+data.id); 
          backups_table.row(row).data(data);			
		}
	}, false);

	backups_source.addEventListener('Status', function(e) {
          var data = JSON.parse(e.data);
          var row = backups_table.row('#'+data.id); 
          backups_table.row(row).data(data);
	}, false);

	backups_source.addEventListener('Deleted', function(e) {
        console.log('deleted');
	  var data = JSON.parse(e.data);
      var row = backups_table.row('#'+data.id).remove().draw();
            new PNotify({
                title: "Domain deleted",
                text: "Domain "+data.name+" has been deleted",
                hide: true,
                delay: 2000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'info'
            });
	}, false);
    
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

    int_table=$('#table-disposables').DataTable({
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
                "defaultContent": '<button id="btn-disposable_desktops-delete" class="btn btn-xs" type="button"  data-placement="top" style="display:none"><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-disposable_desktops-edit" class="btn btn-xs" type="button"  data-placement="top" style="display:none"><i class="fa fa-pencil" style="color:darkblue"></i></button>'
				},
                ],
			 "order": [[1, 'asc']],
			 "columnDefs": [ {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
							  return renderDisposables(full);
							}}]
    } );        
 
     $('#table-disposablesx').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
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
							//~ api.ajax('/domains/update','POST',{'pk':data['id'],'name':'status','value':'Stopping'}).done(function(data) {
                			//~ }); 
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
