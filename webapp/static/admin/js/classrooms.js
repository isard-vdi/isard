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

    var gridster_defaults = {
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
    
    $('.top_nav').hide()
    $('#menu_toggle').click()

    $('#classroom').on('change', function () {
        action=$(this).val();
        console.log(action)
        $('#classroom_name').html(action);
        gridster = $(".gridster ul").gridster(gridster_defaults).data('gridster');
        socket.emit('classroom_get',{'place_id':action});
        menuEdit(true);
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
            menuEdit(true);
    });	

   $('.menu-add-one').on( 'click', function () {
       gridster.add_widget(tableDesktopHtml(gridHeight+1,1,'ip','hostname'),1,1, gridHeight+1, 1);
       //~ enableActions();
   });
   
   $('.menu-reset').on( 'click', function () {
        menuEdit(false);
    });
   
   
    $('.menu-save').on( 'click', function () {
        menuEdit(false);
        data=$('#ClassroomInfo').serializeObject();
        desktops=gridster.serialize()
        socket.emit('classroom_update',{'place':data,'hosts':desktops})            
    });
    
    $("#modalAddClass #send").on('click', function(e){
        var form = $('#modalAdd');
        fData=$('#modalAdd').serializeObject();
        gridWidth=fData.width
        gridHeight=fData.height

            gridster = $(".gridster ul").gridster(gridster_defaults).data('gridster');
    
            $('.gridster ul').css({'padding': '0'});  
            
            i=parseInt(fData.init_ip.substring(fData.network.lastIndexOf(".") + 1, fData.init_ip.length));
            f=fData.height*fData.width
            network=fData.init_ip.substring(0, fData.init_ip.lastIndexOf(".") + 1);

            if(fData.hdirection=='r2l'){
                for (c = fData.height; c >= 1; c--) {
                    for (r = fData.width; r >= 1; r--) {
                        net=network+i.toString()
                        hostname=fData.hostname.replace('{n}',i.toString())
                        console.log(net)
                        gridster.add_widget(tableDesktopHtml(r,c,net,hostname),1,1, r, c);
                        i=i+1;
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
                    }
                }
            }
                        
            $("#modalAdd")[0].reset();
            $("#modalAddClass").modal('hide');
            
            $('#ClassroomInfo #name').val(fData.name)
            $('#ClassroomInfo #description').val(fData.description)
            $('#ClassroomInfo #network').val(fData.network)
            
            //~ enableActions();
        });

    $('.menu-reset').on( 'click', function () {
        gridster.data('gridster').destroy();
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
        console.log('received class data')
        console.log(data);
        place=data['place']
        data=data['hosts']
            $('#ClassroomInfo #name').val(place.name)
            $('#ClassroomInfo #description').val(place.description)
            $('#ClassroomInfo #network').val(place.network)
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


function menuEdit(on){
    if(on){
        $('#classroom_init').hide();
        $('#classroom_edit').show();
    }else{
        $('#classroom_edit').hide();
        $('#classroom_init').show();        
    }
}
