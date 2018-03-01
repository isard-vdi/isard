/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

 
$(document).ready(function() {

    int_table=$('#interfaces').DataTable({
			"ajax": {
				"url": "/admin/table/interfaces/get",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
				{ "data": "name"},
				{ "data": "description"},
                { "data": "net"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[1, 'asc']]
    } );

    $('#interfaces').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });

	$('.add-new-interface').on( 'click', function () {
            $("#modalInterface #modalAddInterface")[0].reset();
            //~ setAlloweds_add('#alloweds-interface-add');
			$('#modalInterface').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalInterface #modalAddInterface').parsley();
            setAlloweds_add('#alloweds-interface-add');
            
    window.Parsley.addValidator('cidr', {
      validateString: function(value, id) {
                var ip = "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])(\/([0-9]|[1-2][0-9]|3[0-2]))$";
                return value.match(ip);
      },
      messages: {
        en: 'This string is not CIDR format'
      }
    });

	});



 //~ $.validator.addMethod('IP4Checker', function(value) {
            //~ var ip = "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])(\/([0-9]|[1-2][0-9]|3[0-2]))$";
                //~ return value.match(ip);
            //~ }, 'Invalid IP address');



    $("#modalInterface #send").on('click', function(e){
            var form = $('#modalAddInterface');

            form.parsley().validate();
            data=$('#modalAddInterface').serializeObject();
            data=replaceAlloweds_arrays(data)
            //~ socket.emit('domain_virtbuilder_add',data)
            //~ if (form.parsley().isValid()){
                //~ template=$('#modalAddDesktop #template').val();
                //~ console.log('TEMPLATE:'+template)
                //~ if (template !=''){
                    //~ var queryString = $('#modalAdd').serialize();
                    //~ data=$('#modalAdd').serializeObject();
                    //~ socket.emit('domain_add',data)
                //~ }else{
                    //~ $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    //~ $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                //~ }
            //~ }
        });

    // DISKS
    disks_table=$('#disks').DataTable({
			"ajax": {
				"url": "/admin/table/disks/get",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
				{ "data": "name"},
				{ "data": "description"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[1, 'asc']]
    } );

    $('#disks').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
        //~ console.log($(this).attr('id'),data);
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });

    
    // GRAPHICS
    graphics_table=$('#graphics').DataTable({
			"ajax": {
				"url": "/admin/table/graphics/get",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
				{ "data": "name"},
				{ "data": "description"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[1, 'asc']]
    } );

    $('#graphics').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
        //~ console.log($(this).attr('id'),data);
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });
    
	$('.add-new-graphics').on( 'click', function () {
            $("#modalGraphics #modalAddGraphics")[0].reset();
			$('#modalGraphics').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalGraphics #modalAddGraphics').parsley();
            setAlloweds_add('#alloweds-graphics-add');
	});

    $("#modalGraphics #send").on('click', function(e){
            var form = $('#modalAddGraphics');
            form.parsley().validate();
            data=$('#modalAddGraphics').serializeObject();
            data=replaceAlloweds_arrays(data)
            //~ socket.emit('domain_virtbuilder_add',data)
            //~ if (form.parsley().isValid()){
                //~ template=$('#modalAddDesktop #template').val();
                //~ console.log('TEMPLATE:'+template)
                //~ if (template !=''){
                    //~ var queryString = $('#modalAdd').serialize();
                    //~ data=$('#modalAdd').serializeObject();
                    //~ socket.emit('domain_add',data)
                //~ }else{
                    //~ $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    //~ $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                //~ }
            //~ }
        });   
        
        
         
    // VIDEOS
    videos_table=$('#videos').DataTable({
			"ajax": {
				"url": "/admin/table/videos/get",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
				{ "data": "name"},
				{ "data": "description"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[1, 'asc']]
    } );

    $('#videos').find(' tbody').on( 'click', 'button', function () {
        var data = int_table.row( $(this).parents('tr') ).data();
        //~ console.log($(this).attr('id'),data);
        //~ switch($(this).attr('id')){
            //~ case 'btn-play':        
                //~ break;
    });
    
	$('.add-new-videos').on( 'click', function () {
            $("#modalVideos #modalAddVideos")[0].reset();
			$('#modalVideos').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalVideos #modalAddVideos').parsley();
            setAlloweds_add('#alloweds-videos-add');
            setRangeSliders();
	});

    $("#modalVideos #send").on('click', function(e){
            var form = $('#modalAddVideos');
            form.parsley().validate();
            data=$('#modalAddVideos').serializeObject();
            data=replaceAlloweds_arrays(data)
            //~ socket.emit('domain_virtbuilder_add',data)
            //~ if (form.parsley().isValid()){
                //~ template=$('#modalAddDesktop #template').val();
                //~ console.log('TEMPLATE:'+template)
                //~ if (template !=''){
                    //~ var queryString = $('#modalAdd').serialize();
                    //~ data=$('#modalAdd').serializeObject();
                    //~ socket.emit('domain_add',data)
                //~ }else{
                    //~ $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    //~ $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                //~ }
            //~ }
        }); 

    function setRangeSliders(id){
        				$("#videos-heads").ionRangeSlider({
						  type: "single",
						  min: 1,
						  max: 4,
                          step:1,
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider").update();
        				$("#videos-ram").ionRangeSlider({
						  type: "single",
						  min: 8000,
						  max: 128000,
                          step:8000,
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider").update();
        				$("#videos-vram").ionRangeSlider({
						  type: "single",
						  min: 8000,
						  max: 128000,
                          step:8000,
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider").update();                          
    }



    // VIDEOS
    boots_table=$('#boots').DataTable({
			"ajax": {
				"url": "/admin/table/boots/get",
				"dataSrc": ""
			},
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
				{ "data": "name"},
				{ "data": "description"},
				{
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "defaultContent": '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
				},                
                ],
			 "order": [[1, 'asc']]
    } );
    

    reconnect=-1;
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_users');
     
    socket.on('connect', function() {
        connection_done();
        reconnect+=1;
        if(reconnect){
            console.log(reconnect+' reconnects to websocket. Refreshing datatables');
            table.ajax.reload();
            // Should have a route to update quota via ajax...
        }
        console.log('Listening users namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });
    
    socket.on('user_quota', function(data) {
        console.log('Quota update')
        var data = JSON.parse(data);
        drawUserQuota(data);
    });

        
});
