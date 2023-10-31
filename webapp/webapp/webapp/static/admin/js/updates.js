/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/
table={}
$(document).ready(function() {
    $.ajax({
        type: "GET",
        url: '/admin/downloads',
        dataType: 'json',
        success: function (resp) {
          $('.registered').show();
          load_data();
        },
        error: function (xhr, ajaxOptions, thrownError) {
            if (xhr.status == 504) {
                $('.not_connected').show();
            } else {
                $('.not_registered').show();
                $('.not_registered').find('button').on('click', function(){
                    $.ajax({
                        type: "POST",
                        url: '/api/v3/admin/downloads/register',
                        dataType: 'json',
                        success: function (resp) {
                            $('.not_registered').hide();
                            $('.registered').show();
                            load_data();
                        },
                        error: function (xhr, ajaxOptions, thrownError) {
                            $('.not_registered').hide();
                            $('.not_connected').show();
                        }
                    });
                });
            }
        }
      })
})



function load_data(){
    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
    function socketio_on(){
        socket.on('desktop_delete', function(){
            table['domains'].ajax.reload();
        });
    
        socket.on('media_delete', function(){
            table['media'].ajax.reload();
        });
    }

    table['domains']=$('#domains_tbl').DataTable({
        "ajax": {
            "url": "/admin/downloads/domains",
            "dataSrc": "",
            "type" : "GET",
            "data": function(d){return JSON.stringify({})}
        },
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
            "emptyTable": "No available downloads"
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
         "order": [[3, 'desc'],[2,'asc']],
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
                            if(full.status == 'Available'){
                                return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
                            }
                            if(full.status == 'Downloading' || full.status == 'Unknown'){
                                return '<button id="btn-abort" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-stop" style="color:darkred"></i></button>'
                            }
                            if(full.status == 'Downloaded' || full.status == 'Failed' || full.status == 'FailedDeleted' || full.status == 'Stopped' || full.status == 'DownloadAborting'){
                                return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                            }
                            if(full.status == 'DownloadFailed'){
                                return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button> \
                                    <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                            }
                            return '<i class="fa fa-spinner fa-pulse fa-fw"></i>'
                        }}],

            "initComplete": function(settings, json){
                socket.on('desktop_data', function(data){
                    var data = JSON.parse(data);
                    dtUpdateOnly(table['domains'],data);
                });

                socket.on('desktop_delete', function(data){
                    var data = JSON.parse(data);
                    table['domains'].row('#'+data.id).remove().draw();
                });
            }
    } );

    $('#domains_tbl').find(' tbody').on( 'click', 'button', function () {
        var id = table['domains'].row( $(this).parents('tr') ).data()['id'];
        switch($(this).attr('id')){
            case 'btn-download':
                $(this).html('<i class="fa fa-spinner fa-pulse fa-fw"></i>')
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/downloads/download/domains/" + id,
                    data: JSON.stringify(table['domains'].row( $(this).parents('tr') ).data()),
                    success: function(data){table['domains'].ajax.reload();}
                })
                break;
            case 'btn-abort':
                $(this).html('<i class="fa fa-spinner fa-pulse fa-fw"></i>')
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/downloads/abort/domains/" + id,
                    data: JSON.stringify({}),
                    success: function(data){table['domains'].ajax.reload();}
                })
                break;
            case 'btn-delete':
                $(this).html('<i class="fa fa-spinner fa-pulse fa-fw"></i>')
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/downloads/delete/domains/" + id,
                    data: JSON.stringify({}),
                    success: function(data){table['domains'].ajax.reload();}
                })
                break;
            };
    });

    table['media']=$('#media_tbl').DataTable({
            "ajax": {
                "url": "/admin/downloads/media",
                "dataSrc": "",
                "type" : "GET",
                "data": function(d){return JSON.stringify({})}
            },
            "language": {
                "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No available downloads"
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
            "order": [[3, 'desc'],[2,'asc']],
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
                                if(['Available', 'deleted'].includes(full.status)){
                                    return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
                                }
                                if(full.status == 'Downloading' || full.status == 'Unknown'){
                                    return '<button id="btn-abort" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-stop" style="color:darkred"></i></button>'
                                }
                                if(full.status == 'Downloaded' || full.status == 'Failed' || full.status == 'FailedDeleted' || full.status == 'Stopped' || full.status == 'DownloadAborting'){
                                    return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                }
                                if(full.status == 'DownloadFailed'){
                                    console.log(full.status)
                                    return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button> \
                                        <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                }
                                return '<i class="fa fa-spinner fa-pulse fa-fw"></i>'
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
        var id = table['media'].row( $(this).parents('tr') ).data()['id'];
        switch($(this).attr('id')){
            case 'btn-download':
                $(this).html('<i class="fa fa-spinner fa-pulse fa-fw"></i>')
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/downloads/download/media/" + id,
                    data: JSON.stringify(table['media'].row( $(this).parents('tr') ).data()),
                    success: function(data){table['media'].ajax.reload();}
                })
                break;
            case 'btn-abort':
                $(this).html('<i class="fa fa-spinner fa-pulse fa-fw"></i>')
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/downloads/abort/media/" + id,
                    data: JSON.stringify({}),
                    success: function(data){table['media'].ajax.reload();}
                })
                break;
            case 'btn-delete':
                $(this).html('<i class="fa fa-spinner fa-pulse fa-fw"></i>')
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/downloads/delete/media/" + id,
                    data: JSON.stringify({}),
                    success: function(data){table['media'].ajax.reload();}
                })
                break;
            };
    });

    table['virt_install']=$('#virt_install_tbl').DataTable({
            "ajax": {
                "url": "/admin/downloads/virt_install",
                "dataSrc": "",
                "type" : "GET",
                "data": function(d){return JSON.stringify({})}
            },
            "language": {
                "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No available downloads"
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
                                if(full['new']){
                                    return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
                                }else{
                                    return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                }
                            }}]
    } );

    $('#virt_install_tbl').find(' tbody').on( 'click', 'button', function () {
        var id = table['virt_install'].row( $(this).parents('tr') ).data()['id'];
        switch($(this).attr('id')){
            case 'btn-download':
                $(this).html('<i class="fa fa-spinner fa-pulse fa-fw"></i>')
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/downloads/download/virt_install/" + id,
                    data: JSON.stringify(table['virt_install'].row( $(this).parents('tr') ).data()),
                    success: function(data){table['virt_install'].ajax.reload();}
                })
                break;
            case 'btn-delete':
                $(this).html('<i class="fa fa-spinner fa-pulse fa-fw"></i>')
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/downloads/delete/virt_install/" + id,
                    data: JSON.stringify({}),
                    success: function(data){table['virt_install'].ajax.reload();}
                })
                break;
            };
    });

    table['videos']=$('#videos_tbl').DataTable({
            "ajax": {
                "url": "/admin/downloads/videos",
                "dataSrc": "",
                "type" : "GET",
                "data": function(d){return JSON.stringify({})}
            },
            "language": {
                "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No available downloads"
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
                                if(full['new']){
                                    return '<button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button>'
                                }else{
                                    return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                                }
                            }}]
    } );

    $('#videos_tbl').find(' tbody').on( 'click', 'button', function () {
        var id = table['videos'].row( $(this).parents('tr') ).data()['id'];
        switch($(this).attr('id')){
            case 'btn-download':
                $(this).html('<i class="fa fa-spinner fa-pulse fa-fw"></i>')
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/downloads/download/videos/" + id,
                    data: JSON.stringify(table['videos'].row( $(this).parents('tr') ).data()),
                    success: function(data){table['videos'].ajax.reload();}
                })
                break;
            case 'btn-delete':
                $(this).html('<i class="fa fa-spinner fa-pulse fa-fw"></i>')
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/downloads/delete/videos/" + id,
                    data: JSON.stringify({}),
                    success: function(data){table['videos'].ajax.reload();}
                })
                break;
            };
    });

    $('.update-all').on( 'click', function () {
        id=$(this).attr('id')
        new PNotify({
            title: 'Warning!',
            text: 'You are about to download all items in list!',
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
        }).get().on('pnotify.confirm', function(){
            $.ajax({
                type: "POST",
                url:"/api/v3/admin/downloads/download/" + id,
                success: function(data){table[id].ajax.reload();}
            });
        })
    })

    table['viewers']=$('#viewers_tbl').DataTable({
            "ajax": {
                "url": "/admin/downloads/viewers",
                "dataSrc": "",
                "type" : "GET",
                "data": function(d){return JSON.stringify({})}
            },
            "language": {
                "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "emptyTable": "No available downloads"
            },
            "rowId": "id",
            "deferRender": true,
            "columns": [
                {"data": "icon"},
                {"data": "name"},
                {"data": null,
                'defaultContent': ''},
                ],
            "order": [[0, 'asc'],[1,'desc'],[2,'asc']],
            "columnDefs": [
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
                                    return '<a href="'+full['url-web']+'"><button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkblue"></i></button></a>'
                            }}]
    } );
}

function renderName(data){
        return '<div class="block_content" > \
                <h4 class="title" style="margin-bottom: 0.1rem; margin-top: 0px;"> \
                <a>'+data.name+'</a> \
                </h4> \
                  <p class="excerpt" >'+data.description+'</p> \
                   </div>'
}

function renderProgress(data){
            perc = data.progress.received_percent
            if(!('progress' in data) || !('received_percent' in data['progress'])){
                return ""
            }
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
