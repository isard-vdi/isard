/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$(document).ready(function() {
    var gridster
    $('.top_nav').hide()
    $('#menu_toggle').click()

    $('#classroom').on('change', function () {
        action=$(this).val();
        console.log(gridster.serialize())
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
                                      max: 10,
                                      grid: true,
                                      disable: false
                                      }).data("ionRangeSlider");
            $("#height").ionRangeSlider({
                                      type: "single",
                                      min: 1,
                                      max: 10,
                                      grid: true,
                                      disable: false
                                      }).data("ionRangeSlider");
    });	

    $("#modalAddClass #send").on('click', function(e){
        var form = $('#modalAdd');
        data=$('#modalAdd').serializeObject();
        
        gridster = $(".gridster ul").gridster({
            widget_margins: [5, 5],
            widget_base_dimensions: [100, 100],
              serialize_params: function ($w, wgd) {
                return {
                  id: $w.data('ip'),
                  mac: $w.data('mac'),
                  hostname: $w.data('hostname'),
                  description: $w.data('description'),
                  col: wgd.col,
                  row: wgd.row,
                  size_x: wgd.size_x,
                  size_y: wgd.size_y,
                };
            }
        }).data('gridster');
            //~ $(function() {
                //~ $('.grid-stack').gridstack({
                                //~ width: data.width,
                                //~ cellHeight: 100,
                                //~ cellWidth: 10,
                                //~ verticalMargin: 5,
                                //~ horizontalMargin: 5,
                                    //~ resizable: {
                                //~ handles: 'e'
                            //~ }
                //~ });
            //~ });
            //~ gswidth=1;
            //~ if(data.width>6){gswidth=1;}
            //~ console.log(gswidth);
            for (c = 1; c <= data.height; c++) {
                for (r = 1; r <= data.width; r++) {
                    gridster.add_widget('<li data-ip="192" data-mac="aa" data-hostname="n2a" data-description="desc" class="text-center" style="color:White">\
                                              <a class="add-new"><span style="color:DarkBlue; "><i class="fa fa-edit"></i></span></a>\
                                              <i class="fa fa-desktop fa-4x"></i>\
                                              <a class="add-new"><span style="color:DarkRed; "><i class="fa fa-remove"></i></span></a>\
                                              <span style="line-height:10px;">192.168.130.190</span>\
                                              <span style="line-height:10px;">n2m 04</span>\
                                              <span style="font-size:80%;line-height:10px;">AA:BB:CC:DD:EE:FF</span>\
                                            </li>',1,1, r, c);
                }
            }
        });
    

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
