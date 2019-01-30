/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/
table={}
$(document).ready(function() {
    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_admins');
     
    socket.on('connect', function() {
        connection_done();
        socket.emit('join_rooms',['media','domains'])
        console.log('Listening media namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
    socket.on('user_quota', function(data) {
        console.log('Quota update')
        var data = JSON.parse(data);
        drawUserQuota(data);
    });



    table['domains']=$('#domains_tbl').DataTable({
			"ajax": {
				"url": "/admin/updates/domains/",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No updates available"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
                {"data": null,
                 'defaultContent': ''},
				{"data": "icon"},
				{"data": "name"},
                {"data": null, "width": "130px",
                 'defaultContent': ''},
                {"data": null,
                 'defaultContent': ''},                               
                ],
			 "order": [[0, 'desc'],[1,'desc'],[2,'asc']],
			 "columnDefs": [{
							"targets": 0,
							"render": function ( data, type, full, meta ) {
                                if(full['new']){
                                    return '<span class="label label-success pull-right">New</span>';
                                }
                                if(full.status.startsWith('Fail')){
                                    return '<span class="label label-danger pull-right">'+full.status+'</span>';
                                }
                                if(full.status.endsWith('ing')){
                                    return '<span class="label label-warning pull-right">'+full.status+'</span>';
                                } 
                                //~ if(full.status=='Downloaded'){
                                    //~ return '<span class="label label-info pull-right">'+full.status+'</span>';
                                //~ } 
                                if(full.status == 'Stopped'){full.status='Downloaded'}                                                                     
                                return '<span class="label label-info pull-right">'+full.status+'</span>';
							}},
                            {
							"targets": 1,
							"render": function ( data, type, full, meta ) {
                                return renderIcon(full)
							}},
                            {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
                                //~ return full.create_dict.hardware.disks['0'].file;
                                return renderName(full)
							}},
                            {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
                                //~ if(full.status == 'Downloaded' || full.status == 'Stopped'){
                                    //~ return 'Downloaded';
                                //~ }media
                                if(full.status == 'Downloading'){
                                    return renderProgress(full);
                                }
                                if('progress' in full){return full.progress.total;}
							}},
                            {
							"targets": 4,
							"render": function ( data, type, full, meta ) {
                                //~ console.log(full.status+' '+full.id)
                                if(full.status == 'Available' || full.status == "DownloadFailed"){
                                    return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
                                }
                                if(full.status == 'Downloading'){
                                    return '<button id="btn-abort" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-stop" style="color:darkred"></i></button>'
                                }
                                if(full.status == 'Downloaded' || full.status == 'Stopped'){
                                    return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                } 
                                return full.status;                               
							}}],

                "initComplete": function(settings, json){
                    socket.on('desktop_data', function(data){
                        var data = JSON.parse(data);
                        if(data['id'].includes('_downloaded_')){
                            dtUpdateInsert(table['domains'],data,false);
                            //~ setDomainDetailButtonsStatus(data.id, data.status);
                        }
                    });

                    socket.on('desktop_delete', function(data){
                        var data = JSON.parse(data);
                        if(data['id'].includes('_downloaded_')){
                            var row = table['domains'].row('#'+data.id).remove().draw();
                        }
                    });                
                }                            
                            
                            
    } );

    $('#domains_tbl').find(' tbody').on( 'click', 'button', function () {
        var datarow = table['domains'].row( $(this).parents('tr') ).data();
        var id = datarow['id'];
        switch($(this).attr('id')){
            case 'btn-download':
                api.ajax('/admin/updates/download/domains/'+id,'POST',{}).done(function(data) {
                    //~ dtUpdateInsert(table['domains'],id,false);
                    table['domains'].ajax.reload();
                      //~ table['domains'].ajax.reload();
                  }); 
                break;
            case 'btn-abort':
                api.ajax('/admin/updates/abort/domains/'+id,'POST',{}).done(function(data) {
                    //~ dtUpdateInsert(table['domains'],id,false);
                    table['domains'].ajax.reload();
                      //~ table['domains'].ajax.reload();
                  }); 
                break;
            case 'btn-delete':
                api.ajax('/admin/updates/delete/domains/'+id,'POST',{}).done(function(data) {
                    table['domains'].ajax.reload();
                   //~ table['domains'].row('#'+id).remove().draw();
                  }); 
                break;
            };  
    });



    table['media']=$('#media_tbl').DataTable({
			"ajax": {
				"url": "/admin/updates/media/",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No updates available"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
                {"data": null,
                 'defaultContent': ''},
				{"data": "icon"},
				{"data": "name"},
                {"data": null, "width": "130px",
                 'defaultContent': ''},
                {"data": null,
                 'defaultContent': ''},                               
                ],
			 "order": [[0, 'desc'],[1,'desc'],[2,'asc']],
			 "columnDefs": [{
							"targets": 0,
							"render": function ( data, type, full, meta ) {
                                if(full['new']){
                                    return '<span class="label label-success pull-right">New</span>';
                                }
                                if(full.status.startsWith('Fail')){
                                    return '<span class="label label-danger pull-right">'+full.status+'</span>';
                                }
                                if(full.status.endsWith('ing')){
                                    return '<span class="label label-warning pull-right">'+full.status+'</span>';
                                } 
                                //~ if(full.status=='Downloaded'){
                                    //~ return '<span class="label label-info pull-right">'+full.status+'</span>';
                                //~ }   
                                if(full.status == 'Stopped'){full.status='Downloaded'}                                                                 
                                return '<span class="label label-info pull-right">'+full.status+'</span>';
							}},
                            {
							"targets": 1,
							"render": function ( data, type, full, meta ) {
                                return renderIcon(full)
							}},
                            {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
                                return renderName(full)
							}},
                            {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
                                if(full.status == 'Downloading'){
                                    return renderProgress(full);
                                }
                                if('progress' in full){return full.progress.total;}
							}},
                            {
							"targets": 4,
							"render": function ( data, type, full, meta ) {
                                //~ console.log(full.status+' '+full.id)
                                if(full.status == 'Available' || full.status == "DownloadFailed"){
                                    return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
                                }
                                if(full.status == 'Downloading'){
                                    return '<button id="btn-abort" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-stop" style="color:darkred"></i></button>'
                                }
                                if(full.status == 'Downloaded' || full.status == 'Stopped'){
                                    return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                } 
                                return full.status;                                
							}}],
                "initComplete": function(settings, json){
                    socket.on('media_data', function(data){
                        var data = JSON.parse(data);
                            dtUpdateOnly(table['media'],data);
                    });

                    socket.on('media_delete', function(data){
                        var data = JSON.parse(data);
                        var row = table['media'].row('#'+data.id).remove().draw();
                    });                    
                                      
                }
                            
                            
    } );




    $('#media_tbl').find(' tbody').on( 'click', 'button', function () {
        var datarow = table['media'].row( $(this).parents('tr') ).data();
        //~ console.log($(this).attr('id'),datarow);
        switch($(this).attr('id')){
            case 'btn-download':
                api.ajax('/admin/updates/download/media/'+datarow['id'],'POST',{}).done(function(data) {
                    //~ dtUpdateInsert(table['media'],datarow['id'],false);
                      //~ console.log(datarow['id'])
                      table['media'].ajax.reload();
                  }); 
                break;
            case 'btn-abort':
                api.ajax('/admin/updates/abort/media/'+datarow['id'],'POST',{}).done(function(data) {
                    //~ dtUpdateInsert(table['media'],datarow['id'],false);
                      //~ console.log(datarow['id'])
                      table['media'].ajax.reload();
                  }); 
                break;
            case 'btn-delete':
                api.ajax('/admin/updates/delete/media/'+datarow['id'],'POST',{}).done(function(data) {
                    table['media'].ajax.reload();
                   //~ table['media'].row('#'+datarow['id']).remove().draw();
                  }); 
                break;
            };  
    });
    
    table['builders']=$('#builders_tbl').DataTable({
			"ajax": {
				"url": "/admin/updates/builders/",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No updates available"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
                {"data": null,
                 'defaultContent': ''},
				{"data": "icon"},
				{"data": "name"},
                {"data": null,
                 'defaultContent': ''},                               
                ],
			 "order": [[0, 'desc'],[1,'desc'],[2,'asc']],
			 "columnDefs": [{
							"targets": 0,
							"render": function ( data, type, full, meta ) {
                                if(full['new']){
                                    return '<span class="label label-success pull-right">New</span>';
                                }else{
                                    return '<span class="label label-info pull-right">Downloaded</span>';
                                }
							}},
                            {
							"targets": 1,
							"render": function ( data, type, full, meta ) {
                                return renderIcon(full)
							}},
                            {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
                                return renderName(full)
							}},
                            {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
                                //~ console.log(full.status+' '+full.id)
                                if(full.status == 'Available' || full.status == "DownloadFailed"){
                                    return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
                                }
                                if(full.status == 'Downloading'){
                                    return '<button id="btn-abort" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-stop" style="color:darkred"></i></button>'
                                }
                                if(full.status == 'Downloaded' || full.status == 'Stopped'){
                                    return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                } 
                                return full.status;                                
							}}]
    } );

    $('#builders_tbl').find(' tbody').on( 'click', 'button', function () {
        var datarow = table['builders'].row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
            case 'btn-download':
                api.ajax('/admin/updates/download/builders/'+datarow['id'],'POST',{}).done(function(data) {
                      table['builders'].ajax.reload();
                  }); 
                break;
            case 'btn-delete':
                api.ajax('/admin/updates/delete/builders/'+datarow['id'],'POST',{}).done(function(data) {
                   table['builders'].ajax.reload();
                   //~ table['virt_install'].row('#'+datarow['id']).remove().draw();
                  }); 
                break;
            }; 
    });
    
    table['virt_builder']=$('#virt_builder_tbl').DataTable({
			"ajax": {
				"url": "/admin/updates/virt_builder/",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No updates available"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
                {"data": null,
                 'defaultContent': ''},
				{"data": "icon"},
				{"data": "name"},
                {"data": null,
                 'defaultContent': ''},                               
                ],
			 "order": [[0, 'asc'],[1,'desc'],[2,'asc']],
			 "columnDefs": [{
							"targets": 0,
							"render": function ( data, type, full, meta ) {
                                if(full['new']){
                                    return '<span class="label label-success pull-right">New</span>';
                                }else{
                                    return '<span class="label label-info pull-right">Downloaded</span>';
                                }
							}},
                            {
							"targets": 1,
							"render": function ( data, type, full, meta ) {
                                return renderIcon(full)
							}},
                            {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
                                return renderName(full)
							}},
                            {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
                                //~ console.log(full.status+' '+full.id)
                                if(full.status == 'Available' || full.status == "DownloadFailed"){
                                    return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
                                }
                                if(full.status == 'Downloading'){
                                    return '<button id="btn-abort" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-stop" style="color:darkred"></i></button>'
                                }
                                if(full.status == 'Downloaded' || full.status == 'Stopped'){
                                    return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                } 
                                return full.status;                                
							}}]
    } );

    $('#virt_builder_tbl').find(' tbody').on( 'click', 'button', function () {
        var datarow = table['virt_builder'].row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
            case 'btn-download':
                api.ajax('/admin/updates/download/virt_builder/'+datarow['id'],'POST',{}).done(function(data) {
                      table['virt_builder'].ajax.reload();
                  }); 
                break;
            case 'btn-delete':
                api.ajax('/admin/updates/delete/virt_builder/'+datarow['id'],'POST',{}).done(function(data) {
                   table['virt_builder'].ajax.reload();
                   //~ table['virt_install'].row('#'+datarow['id']).remove().draw();
                  }); 
                break;
            }; 
    });
    
    table['virt_install']=$('#virt_install_tbl').DataTable({
			"ajax": {
				"url": "/admin/updates/virt_install/",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No updates available"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
                {"data": null,
                 'defaultContent': ''},
				{"data": "icon"},
				{"data": "name"},
                {"data": null,
                 'defaultContent': ''},                               
                ],
			 "order": [[0, 'asc'],[1,'desc'],[2,'asc']],
			 "columnDefs": [{
							"targets": 0,
							"render": function ( data, type, full, meta ) {
                                if(full['new']){
                                    return '<span class="label label-success pull-right">New</span>';
                                }else{
                                    return '<span class="label label-info pull-right">Downloaded</span>';
                                }
							}},
                            {
							"targets": 1,
							"render": function ( data, type, full, meta ) {
                                return renderIcon(full)
							}},
                            {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
                                return renderName(full)
							}},
                            {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
                                //~ console.log(full.status+' '+full.id)
                                if(full['new']){
                                    return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
                                }else{
                                    return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                } 
							}}]
    } );

    $('#virt_install_tbl').find(' tbody').on( 'click', 'button', function () {
        var datarow = table['virt_install'].row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
            case 'btn-download':
                api.ajax('/admin/updates/download/virt_install/'+datarow['id'],'POST',{}).done(function(data) {
                      table['virt_install'].ajax.reload();
                  }); 
                break;
            case 'btn-delete':
                api.ajax('/admin/updates/delete/virt_install/'+datarow['id'],'POST',{}).done(function(data) {
                   table['virt_install'].ajax.reload();
                   //~ table['virt_install'].row('#'+datarow['id']).remove().draw();
                  }); 
                break;
            };         
    });

    table['videos']=$('#videos_tbl').DataTable({
			"ajax": {
				"url": "/admin/updates/videos/",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No updates available"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
                {"data": null,
                 'defaultContent': ''},
				{"data": "icon"},
				{"data": "name"},
                {"data": null,
                 'defaultContent': ''},                               
                ],
			 "order": [[0, 'asc'],[1,'desc'],[2,'asc']],
			 "columnDefs": [{
							"targets": 0,
							"render": function ( data, type, full, meta ) {
                                if(full['new']){
                                    return '<span class="label label-success pull-right">New</span>';
                                }else{
                                    return '<span class="label label-info pull-right">Downloaded</span>';
                                }
							}},
                            {
							"targets": 1,
							"render": function ( data, type, full, meta ) {
                                return renderIcon(full)
							}},
                            {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
                                return renderName(full)
							}},
                            {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
                                //~ console.log(full.status+' '+full.id)
                                if(full['new']){
                                    return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
                                }else{
                                    return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                } 
							}}]
    } );

    $('#videos_tbl').find(' tbody').on( 'click', 'button', function () {
        var datarow = table['videos'].row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
            case 'btn-download':
                api.ajax('/admin/updates/download/videos/'+datarow['id'],'POST',{}).done(function(data) {
                      table['videos'].ajax.reload();
                  }); 
                break;
            case 'btn-delete':
                api.ajax('/admin/updates/delete/videos/'+datarow['id'],'POST',{}).done(function(data) {
                   table['videos'].ajax.reload();
                   //~ table['virt_install'].row('#'+datarow['id']).remove().draw();
                  }); 
                break;
            };         
    });
    


    
    $('.update-all').on( 'click', function () {
      id=$(this).attr('id')
      api.ajax('/admin/updates/download/'+id,'POST',{}).done(function(data) {
          //~ console.log(id)
          table[id].ajax.reload();
          //~ if(id == 'virt_install'){virt_install_table.ajax.reload();}
      }); 
      // invalidate table
     
    })

    //~ $('.update-one').on( 'click', function () {
      //~ id=$(this).attr('id')
          //~ console.log(id)
     
    //~ })


    table['viewers']=$('#viewers_tbl').DataTable({
			"ajax": {
				"url": "/admin/updates/viewers/",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No updates available"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
                //~ {"data": null,
                 //~ 'defaultContent': ''},
				{"data": "icon"},
				{"data": "name"},
                {"data": null,
                 'defaultContent': ''},                               
                ],
			 "order": [[0, 'asc'],[1,'desc'],[2,'asc']],
			 "columnDefs": [
                            //~ {
							//~ "targets": 0,
							//~ "render": function ( data, type, full, meta ) {
                                //~ if(full['new']){
                                    //~ return '<span class="label label-success pull-right">New</span>';
                                //~ }else{
                                    //~ return '<span class="label label-info pull-right">Downloaded</span>';
                                //~ }
							//~ }},
                            {
							"targets": 0,
							"render": function ( data, type, full, meta ) {
                                return renderIcon(full)
							}},
                            {
							"targets": 1,
							"render": function ( data, type, full, meta ) {
                                return renderName(full)
							}},
                            {
							"targets": 2,
							"render": function ( data, type, full, meta ) {
                                //~ console.log(full.status+' '+full.id)
                                //~ if(full['new']){
                                    return '<a href="'+full['url-web']+'"><button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button></a>'
                                //~ }else{
                                    //~ return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                //~ } 
							}}]
    } );
 
});


function renderName(data){
		return '<div class="block_content" > \
      			<h2 class="title" style="height: 4px; margin-top: 0px;"> \
                <a>'+data.name+'</a> \
                </h2> \
      			<p class="excerpt" >'+data.description+'</p> \
           		</div>'
}

function renderProgress(data){
            perc = data.progress.received_percent
            return data.progress.total+' - '+data.progress.speed_download_average+'/s - '+data.progress.time_left+'<div class="progress"> \
                  <div id="pbid_'+data.id+'" class="progress-bar" role="progressbar" aria-valuenow="'+perc+'" \
                  aria-valuemin="0" aria-valuemax="100" style="width:'+perc+'%"> \
                    '+perc+'%  \
                  </div> \
                </<div> '
}


function renderIcon(data){
    if(data.icon == null){
        return '';
    }
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
