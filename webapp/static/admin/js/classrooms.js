/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


$(document).ready(function() {
    $('.top_nav').hide()
    $('#menu_toggle').click()
         

    $('#classroom').on('change', function () {
        action=$(this).val();
        console.log(action)
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
