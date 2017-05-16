/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$(document).ready(function() {
    var gridster
    var gridHeight=0
    var gridWidth=0
    
    $('.top_nav').hide()
    $('#menu_toggle').click()

    $('#classroom').on('change', function () {
        console.log('emitting')
        action=$(this).val();
        console.log(action)
        socket.emit('classroom_get',{'place_id':action});
        console.log('emitted')
        //~ console.log(gridster.serialize())
    } );


	// DataTable buttons
    $('.add-new').on( 'click', function () {
            $("#modalAdd")[0].reset();
			$('#modalAddClass').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalAdd').parsley();
            $("#width").ionRangeSlider({
                                      type: "single",
                                      min: 1,
                                      max: 8,
                                      grid: true,
                                      disable: false
                                      }).data("ionRangeSlider");
            $("#height").ionRangeSlider({
                                      type: "single",
                                      min: 1,
                                      max: 6,
                                      grid: true,
                                      disable: false
                                      }).data("ionRangeSlider");
    });	

   $('.menu-add-one').on( 'click', function () {
       gridster.add_widget(tableDesktopHtml(gridHeight+1,1,'ip','hostname'),1,1, gridHeight+1, 1);
       //~ enableActions();
   });
    $('.menu-save').on( 'click', function () {
            $("#modalSave")[0].reset();
			$('#modalSaveClass').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalSave').parsley();
            
    });

    $("#modalSaveClass #send").on('click', function(e){
        var form = $('#modalSave');
        data=$('#modalSave').serializeObject();
        desktops=gridster.serialize()
        var items=[];
        for (var i = 0; i < desktops.length; i++) {
            desktops[i]['place_id']=data.name;
            desktops[i]['enabled']=true;
            
            //~ items.push({"description": desktops[i].description ,
                        //~ "desktops_running": [ ],
                        //~ "enabled": true ,
                        //~ "hostname": desktops[i].hostname ,
                        //~ "ip": desktops[i].id ,
                        //~ "loged_user": null ,
                        //~ "mac": desktops[i].mac ,
                        //~ "place_id": data.name ,
                        //~ "position": {
                            //~ "size_y": desktops[i].size_y ,
                            //~ "size_x": desktops[i].size_x ,
                            //~ "col": desktops[i].col,
                            //~ "row": desktops[i].row
                        //~ } ,
                        //~ "status": "Offline" ,
                        //~ "status_time": 0

                    //~ } );
        };
        //~ console.log(data)
        console.log(desktops)
        console.log(items)

        
        socket.emit('classroom_update',{'classroom':data,'desktops':desktops})
    });
    
    $("#modalAddClass #send").on('click', function(e){
        var form = $('#modalAdd');
        fData=$('#modalAdd').serializeObject();
        gridWidth=fData.width
        gridHeight=fData.height
        //~ gridster = $(".gridster ul").gridster({
            //~ widget_margins: [5, 5],
            //~ widget_base_dimensions: [100, 100],
              //~ serialize_params: function ($w, wgd) {
                //~ return {
                  //~ id: $w.data('ip'),
                  //~ mac: $w.data('mac'),
                  //~ hostname: $w.data('hostname'),
                  //~ description: $w.data('description'),
                  //~ col: wgd.col,
                  //~ row: wgd.row,
                  //~ size_x: wgd.size_x,
                  //~ size_y: wgd.size_y,
                //~ };
            //~ }
        //~ }).data('gridster');
    var defaults = {
        //~ widget_selector: '> li',
        //~ widget_margins: [5, 5],
        widget_base_dimensions: [100,100],
        //~ extra_rows: 1,
        //~ extra_cols: 1,
        //~ min_cols: 1,
        //~ min_rows: 15,
        //~ max_size_x: 6,
        //~ max_rows: 9,
        //~ max_cosl:9,
        shift_larger_widgets_down: false,
        autogenerate_stylesheet: true,
        avoid_overlapped_widgets: true,
        serialize_params: function ($w, wgd) {
                return {
                  id: $w.data('ip'),
                  mac: $w.data('mac'),
                  hostname: $w.data('hostname'),
                  description: $w.data('description'),
                  position: {
                      col: wgd.col,
                      row: wgd.row,
                      size_x: wgd.size_x,
                      size_y: wgd.size_y,
                   }
                };
        },
        collision: {},
	//~ static_class: 'custom_class',
	draggable: {
        items: ".gs_w:not(.custom_class)"
    }        
        //~ draggable: {
            //~ distance: 12
        //~ }
    };
            gridster = $(".gridster ul").gridster(defaults).data('gridster');
    
            $('.gridster  ul').css({'padding': '0'});  
            
            i=parseInt(fData.network.substring(fData.network.lastIndexOf(".") + 1, fData.network.length));
            f=fData.height*fData.width
            network=fData.network.substring(0, fData.network.lastIndexOf(".") + 1);
            
            //~ ip=network+(i+r*c).toString();
            //~ for (c = 1; c <= fData.height; c++) {
                //~ for (r = 1; r <= fData.width; r++) {
                    //~ net=network+i.toString()
                    //~ console.log(net)
                    //~ gridster.add_widget(tableDesktopHtml(r,c,net),1,1, r, c);
                    //~ i=i+1;
                    //gridster.add_widget.apply(gridster, [tableDesktopHtml(r,c),1,1, r, c])
                //~ }
            //~ }
            if(fData.hdirection=='r2l'){
                for (c = fData.height; c >= 1; c--) {
                    for (r = fData.width; r >= 1; r--) {
                        net=network+i.toString()
                        hostname=fData.hostname.replace('{n}',i.toString())
                        console.log(net)
                        gridster.add_widget(tableDesktopHtml(r,c,net,hostname),1,1, r, c);
                        i=i+1;
                        //~ gridster.add_widget.apply(gridster, [tableDesktopHtml(r,c),1,1, r, c])
                    }
                }
            }
            if(fData.hdirection=='l2r'){
                for (c = fData.height; c >= 1; c--) {
                    for (r = 1; r <= fData.width; r++) {
                        net=network+i.toString()
                        console.log(net)
                        gridster.add_widget(tableDesktopHtml(r,c,net),1,1, r, c);
                        i=i+1;
                        //~ gridster.add_widget.apply(gridster, [tableDesktopHtml(r,c),1,1, r, c])
                    }
                }
            }
                        
            $("#modalAdd")[0].reset();
            $("#modalAddClass").modal('hide');
            //~ enableActions();
        });

    $('.menu-reset').on( 'click', function () {
        //~ $(".gridster ul").html='';
        gridster.data('gridster').destroy();
        
        //~ $(".gridster").draggable().draggable("destroy");
        //~ $(".gridster").removeData();
    });
    
    function tableDesktopHtml(r,c,net,hostname){
        return '<li data-ip="'+net+'" data-mac="" data-hostname="'+hostname+'" data-description="" class="text-center" style="color:White">\
                                              <a class="desktop-edit"><span style="color:DarkBlue; "><i class="fa fa-edit"></i></span></a>\
                                              <i class="fa fa-desktop fa-4x"></i>\
                                              <a class="desktop-remove"><span style="color:DarkRed; "><i class="fa fa-remove"></i></span></a>\
                                              <span style="line-height:10px;">'+net+'</span>\
                                              <span style="line-height:10px;">'+hostname+'</span>\
                                              <span style="font-size:80%;line-height:10px;">NO MAC</span>\
                                            </li>'       
    }

    //~ function enableActions(){
        $('.gridster').on( 'click', '.desktop-remove', function () {
            console.log('remove')
            $(this).closest('li').addClass("activ");
            gridster.remove_widget($('.activ'));
        });
    //~ }


    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_admins');

    socket.on('connect', function() {
        connection_done();
        //~ socket.emit('join_rooms',['domains'])
        console.log('Listening admins namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });

    socket.on('classroom_data', function(data){
        var data = JSON.parse(data);
    });

    socket.on('classroom_load', function(data){
        var data = JSON.parse(data);
        console.log(data);
        for (var i = 0; i < data.length; i++) {
            console.log(data[i].position.row)
            gridster.add_widget(tableDesktopHtml(data[i].position.col,data[i].position.row,data[i].id,data[i].position.hostname),1,1, data[i].position.col, data[i].position.row);
        }
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

});
