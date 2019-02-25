/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$(document).ready(function() {
    user=$('#user_data').data("userid");

    modal_add_install = $('#modal_add_install').DataTable()
	initialize_modal_all_install_events()
    
	$('.btn-new').on('click', function () {
                if($('.quota-isos .perc').text() >=100){
                    new PNotify({
                        title: "Quota for adding isos full.",
                        text: "Can't create add another iso, quota full.",
                        hide: true,
                        delay: 3000,
                        icon: 'fa fa-alert-sign',
                        opacity: 1,
                        type: 'error'
                    });
                }else{	
                    $("#modalAddMediaForm")[0].reset();
                    $('#modalAddMedia').modal({
                        backdrop: 'static',
                        keyboard: false
                    }).modal('show');
                    $('#modalAddMediaForm').parsley();
                    $('#modalAddMediaForm #name').focus(function(){
                        if($(this).val()=='' && $('#modalAddMediaForm #url').val() !=''){
                            $(this).val($('#modalAddMediaForm #url').val().split('/').pop(-1));
                        }
                    });
                    setAlloweds_add('#modalAddMedia #alloweds-add');
                }
	});

    var table=$('#media').DataTable( {
        "ajax": {
                "url": "/media/get/",
                "dataSrc": ""
				//~ "url": "/admin/tabletest/media/post",
                //~ "contentType": "application/json",
                //~ "type": 'POST',
                //~ "data": function(d){return JSON.stringify({'flatten':false})}            
        },
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
			"deferRender": true,
        "columns": [
				//~ {
                //~ "className":      'details-control',
                //~ "orderable":      false,
                //~ "data":           null,
                //~ "width": "10px",
                //~ "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				//~ },
                { "data": "icon", "width": "10px"},
                { "data": "name"},
                { "data": null, "width": "10px"},
                { "data": "status", "width": "10px"},                
                { "data": null,"width": "150px", "className": "text-center"},
                {"data": null, 'defaultContent': '',"width": "80px"},  
            ],
        "columnDefs": [ 
                            //~ { "className": "dt-right", "targets": [3] },
							{
							"targets": 0,
							"render": function ( data, type, full, meta ) {
							  return renderIcon(full);
							}},
							{
							"targets": 1,
							"render": function ( data, type, full, meta ) {
							  return renderName(full);
							}},
							{
							"targets": 2,
							"render": function ( data, type, full, meta ) {
                                if(!('username' in full)){return full.user;}
							  return full.username;
							}},
							{
							"targets": 3,
							"render": function ( data, type, full, meta ) {
							  return full.status;
							}},
                            {
							"targets": 4,
							"render": function ( data, type, full, meta ) {
                                if(full.status == 'Downloading'){
                                    return renderProgress(full);
                                }
                                if('total' in full.progress){return full.progress.total;}
                                return ''
							}},
                            {
							"targets": 5,
							"render": function ( data, type, full, meta ) { 
                                //~ if(user != full.username && (full.status == 'Downloaded' || full.status == 'Stopped')){
                                    //~ return '<button id="btn-createfromiso" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-desktop" style="color:darkgreen"></i></button>'
                                //~ }
                                //~ }else{
                                    if(full.status == 'Available' || full.status == "DownloadFailed"){
                                        return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button> \
                                                <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                    }
                                    if(full.status == 'Downloading'){
                                        return '<button id="btn-abort" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-stop" style="color:darkred"></i></button>'
                                    }
                                    if(full.status == 'Downloaded' || full.status == 'Stopped'){
                                        return '<button id="btn-createfromiso" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-desktop" style="color:darkgreen"></i></button> \
                                                <button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button> \
                                                <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                    //~ } 
                                }
                                //~ return full.status;                                 
                                }}],
        "initComplete": function() {
                                //~ $('.progress .progress-bar').progressbar();
                                //~ $('.progress-bar').progressbar();
                              }
    } );

    $('#media').find(' tbody').on( 'click', 'button', function () {
        var data = table.row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
            case 'btn-delete':
				new PNotify({
						title: 'Confirmation Needed',
							text: "Are you sure you want to delete this media: "+data.name+"?",
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
                            socket.emit('media_update',{'pk':data.id,'name':'status','value':'Deleting'})
						}).on('pnotify.cancel', function() {
				});
                break;
             case 'btn-abort':
                    //~ var pk=$(this).closest("div").attr("data-pk");
                    //~ console.log('abort:'+pk)
                    //~ var name=$(this).closest("div").attr("data-name");
                    new PNotify({
                            title: 'Confirmation Needed',
                                text: "Are you sure you want to abort this download: "+data.name+"?",
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
                                socket.emit('media_update',{'pk':data.id,'name':'status','value':'DownloadAborting'})
                            }).on('pnotify.cancel', function() {
                    });	             
                break;
             case 'btn-alloweds':
                    modalAllowedsFormShow('media',data)
                break;                
            case 'btn-createfromiso':
                if($('.quota-desktops .perc').text() >=100){
                    new PNotify({
                        title: "Quota for adding new desktop full.",
                        text: "Can't create add another desktop, quota full.",
                        hide: true,
                        delay: 3000,
                        icon: 'fa fa-alert-sign',
                        opacity: 1,
                        type: 'error'
                    });
                }else{	
                    $("#modalAddFromMedia #modalAdd")[0].reset();
                    setHardwareOptions('#modalAddFromMedia','iso');
                    $('#modalAddFromMedia #modalAdd #media').val(data.id);
                    $('#modalAddFromMedia #modalAdd #media_name').html(data.name);
                    $('#modalAddFromMedia #modalAdd #media_size').html(data['progress-total']);
                    $('#modalAddFromMedia').modal({
                        backdrop: 'static',
                        keyboard: false
                    }).modal('show');
                    
                    $('#modalAddFromMedia #modalAdd').parsley();
                    modal_add_install_datatables();
                }
            break;
        };


        //~ $('btn-abort').on('click', function () {

        //~ });
        
        //~ $('btn-delete').on('click', function () {

        //~ });
    
    });    
    
    $("#modalAddMedia #send").on('click', function(e){
            var form = $('#modalAddMediaForm');

            form.parsley().validate();

            if (form.parsley().isValid()){
                data=$('#modalAddMediaForm').serializeObject();
                data=replaceAlloweds_arrays('#modalAddMediaForm #alloweds-add',data)
                socket.emit('media_add',data)
            }
            

        });





    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_users');
     
    socket.on('connect', function() {
        connection_done();
        console.log('Listening users namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
     
    socket.on('user_quota', function(data) {
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

    socket.on('media_data', function(data){
        //~ console.log('add or update')
        var data = JSON.parse(data);
            //~ $('#pbid_'+data.id).data('transitiongoal',data.percentage);
            //~ $('#pbid_').css('width', data.percentage+'%').attr('aria-valuenow', data.percentage).text(data.percentage); 
            //~ $('#psmid_'+data.id).text(data.percentage);
        dtUpdateInsert(table,data,false);
        //~ $('.progress .progress-bar').progressbar();
    });

    
    socket.on('media_delete', function(data){
        //~ console.log('delete')
        var data = JSON.parse(data);
        var row = table.row('#'+data.id).remove().draw();
        new PNotify({
                title: "Media deleted",
                text: "Media "+data.name+" has been deleted",
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
        var data = JSON.parse(data);
        if(data.result){
            $("#modalAddMediaForm")[0].reset();
            $("#modalAddMedia").modal('hide');
            $("#modalAddFromMedia #modalAdd")[0].reset();
            $("#modalAddFromMedia").modal('hide');            
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

    
 } );


function renderProgress(data){ 
            perc = data.progress.received_percent
            return data.progress.total+' - '+data.progress.speed_download_average+'/s - '+data.progress.time_left+'<div class="progress"> \
                  <div id="pbid_'+data.id+'" class="progress-bar" role="progressbar" aria-valuenow="'+perc+'" \
                  aria-valuemin="0" aria-valuemax="100" style="width:'+perc+'%"> \
                    '+perc+'%  \
                  </div> \
                </<div> '
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

function icon(name){
    if(name.startsWith("fa-")){return "<i class='fa "+name+" fa-2x '></i>";}
    if(name.startsWith("fl-")){return "<span class='"+name+" fa-2x'></span>";}
       if(name=='windows' || name=='linux'){
           return "<i class='fa fa-"+name+" fa-2x '></i>";
        }else{
            return "<span class='fl-"+name+" fa-2x'></span>";
		}       
}





// MODAL install FUNCTIONS
function initialize_modal_all_install_events(){
   $('#modal_add_install tbody').on( 'click', 'tr', function () {
        rdata=modal_add_install.row(this).data()
        if ( $(this).hasClass('selected') ) {
            $(this).removeClass('selected');
            $('#modal_add_install').closest('.x_panel').addClass('datatables-error');
            $('#modalInstall #datatables-install-error-status').html('No OS template selected').addClass('my-error');
            
            $('#modalInstall #install').val('');
        }
        else {
            modal_add_install.$('tr.selected').removeClass('selected');
            $(this).addClass('selected');
            $('#modal_add_install').closest('.x_panel').removeClass('datatables-error');
            $('#modalInstall #datatables-install-error-status').empty().removeClass('my-error');   //.html('Selected: '+rdata['name']+'')
            $('#modalInstall #install').val(rdata['id']);
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
				"url": "/media/installs/",
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
    
    $("#modalAddFromMedia #send").on('click', function(e){
            var form = $('#modalAddFromMedia #modalAdd');
            form.parsley().validate();
            
            if (form.parsley().isValid()){
                install=$('#modalAddFromMedia #install').val();
                //~ console.log('install:'+install+'XXX')
                
                //~ if (install !=''){console.log('install not empty')}else{console.log('install empty')}
                
                if (install !=''){
                    data=$('#modalAddFromMedia  #modalAdd').serializeObject();
                    socket.emit('domain_media_add',data)
                }else{                
                    //~ console.log('OK!!')
                        $('#modal_add_install').closest('.x_panel').addClass('datatables-error');
                        $('#modalAddFromMedia #datatables-install-error-status').html('No OS template selected').addClass('my-error');                    
                }
            }        
        
        
        
        
        
        
        
        
        
        
        
        
            //~ var form = $('#modalAddFromMedia #modalAdd');

            //~ form.parsley().validate();

            //~ if (form.parsley().isValid()){
                //~ data=$('#modalAddFromMedia #modalAdd').serializeObject();
                //~ data=replaceAlloweds_arrays(data)
                //~ console.log(data)
                //~ socket.emit('domain_media_add',data)
            //~ }
            

        });    

}


