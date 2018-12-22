/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {
    modal_add_builder = $('#modal_add_builder').DataTable()
	initialize_modal_all_builder_events()

    modal_add_install = $('#modal_add_install').DataTable()
	initialize_modal_all_install_events()

    modal_add_media = $('#modal_add_media').DataTable()
	initialize_modal_all_media_events()
           
	$('.add-new-virtbuilder').on( 'click', function () {
            $("#modalAddFromBuilder #modalAdd")[0].reset();
			setHardwareOptions('#modalAddFromBuilder','disk');

			$('#modalAddFromBuilder').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalAddFromBuilder #modalAdd').parsley();
            modal_add_builder_datatables();
	});

	$('.add-new-media').on( 'click', function () {
            $("#modalAddFromMedia #modalAdd")[0].reset();
			setHardwareOptions('#modalAddFromMedia','iso');
			$('#modalAddFromMedia').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalAddFromMedia #modalAdd').parsley();
            modal_add_install_datatables();
            modal_add_media_datatables();
	});

});

// MODAL BUILDER FUNCTIONS
function initialize_modal_all_builder_events(){
   $('#modal_add_builder tbody').on( 'click', 'tr', function () {
        rdata=modal_add_builder.row(this).data()
        if ( $(this).hasClass('selected') ) {
            $(this).removeClass('selected');
            $('#modal_add_builder').closest('.x_panel').addClass('datatables-error');
            $('#modalBuilder #datatables-error-status').html('No template selected').addClass('my-error');
            
            $('#modalBuilder #builder-id').val('');
            $('#modalBuilder #icon').val('');
            $('#modalBuilder #install-id').val('');
        }
        else {
            modal_add_builder.$('tr.selected').removeClass('selected');
            $(this).addClass('selected');
            $('#modal_add_builder').closest('.x_panel').removeClass('datatables-error');
            $('#modalBuilder #datatables-error-status').empty().html('<b style="color:DarkSeaGreen">Template selected: '+rdata['name']+'</b>').removeClass('my-error');
            $('#modalBuilder #builder-id').val(rdata['builder-id']);
            $('#modalBuilder #builder-options').val(rdata['builder-options']);
            $('#modalBuilder #icon').val(rdata['icon']);
            $('#modalBuilder #install-id').val(rdata['install-id']);
        }
    } );	
        

    $("#modalAddFromBuilder #send").on('click', function(e){
            var form = $('#modalAddFromBuilder #modalAdd');
            //~ form.parsley().validate();
            //~ var queryString = $('#modalAdd').serialize();
            data=$('#modalAddFromBuilder #modalAdd').serializeObject();
            socket.emit('domain_virtbuilder_add',data)
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
        
}

function modal_add_builder_datatables(){
    modal_add_builder.destroy()
    $('#modalBuilder #builder-id').val('');
    $('#modalBuilder #icon').val('');
    $('#modalBuilder #install-id').val('');
    $('#modalBuilder #datatables-error-status').empty()
    
    $('#modal_add_builder thead th').each( function () {
        var title = $(this).text();
        if(title=='Name'){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );
    
	modal_add_builder = $('#modal_add_builder').DataTable({
			"ajax": {
				"url": "/admin/table/builders/get",
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
                //~ { "data": "arch"},
                //~ { "data": "revision"},
                //~ { "data": "size"},
                //~ { "data": "compressed_size"}
				],
			 "order": [[0, 'asc']],	
             "pageLength": 10,	 
	} );  

    modal_add_builder.columns().every( function () {
        var that = this;
 
        $( 'input', this.header() ).on( 'keyup change', function () {
            if ( that.search() !== this.value ) {
                that
                    .search( this.value )
                    .draw();
            }
        } );
    } );

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
				"url": "/admin/table/virt_install/get",
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

}



// MODAL ISOS FUNCTIONS
function initialize_modal_all_media_events(){
   $('#modal_add_media tbody').on( 'click', 'tr', function () {
        rdata=modal_add_media.row(this).data()
        if ( $(this).hasClass('selected') ) {
            $(this).removeClass('selected');
            $('#modal_add_media').closest('.x_panel').addClass('datatables-error');
            $('#modalMedia #datatables-media-error-status').html('No installation media selected').addClass('my-error');
            
            $('#modalMedia #media').val('');
        }
        else {
            modal_add_media.$('tr.selected').removeClass('selected');
            $(this).addClass('selected');
            $('#modal_add_media').closest('.x_panel').removeClass('datatables-error');
            $('#modalMedia #datatables-media-error-status').empty().removeClass('my-error'); //.html('<b style="color:DarkSeaGreen">Template selected: '+rdata['name']+'</b>').removeClass('my-error');
            $('#modalMedia #media').val(rdata['id']);
        }
    } );	
        

    $("#modalAddFromMedia #send").on('click', function(e){
            var form = $('#modalAddFromMedia #modalAdd');
            form.parsley().validate();
            
            if (form.parsley().isValid()){
                media=$('#modalAddFromMedia #media').val();
                install=$('#modalAddFromMedia #install').val();
                if (media !='' && install !=''){
                    //~ var queryString = $('#modalAdd').serialize();
                    data=$('#modalAddFromMedia  #modalAdd').serializeObject();
                    socket.emit('domain_media_add',data)
                }else{                
                    if (media ==''){
                        $('#modal_add_media').closest('.x_panel').addClass('datatables-error');
                        $('#modalAddFromMedia #datatables-media-error-status').html('No media source selected').addClass('my-error');                    
                    }
                    if (install ==''){
                        $('#modal_add_install').closest('.x_panel').addClass('datatables-error');
                        $('#modalAddFromMedia #datatables-install-error-status').html('No OS template selected').addClass('my-error');                    
                    }
                }
            }
        });
}

function modal_add_media_datatables(){
    modal_add_media.destroy()
    $('#modalMedia #media').val('');
    $('#modalMedia #datatables-media-error-status').empty()
    
    $('#modal_add_media thead th').each( function () {
        var title = $(this).text();
        if(title=='Name'){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );
    
	modal_add_media = $('#modal_add_media').DataTable({
			"ajax": {
				"url": "/admin/table/media/get",
				"dataSrc": ""
			},
            "scrollY":        "125px",
            "scrollCollapse": true,
            "paging":         false,
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "zeroRecords":    "No matching media found",
                "info":           "Showing _START_ to _END_ of _TOTAL_ media",
                "infoEmpty":      "Showing 0 to 0 of 0 media",
                "infoFiltered":   "(filtered from _MAX_ total media)"
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{ "data": "name"}
				],
			 "order": [[0, 'asc']],	
             "pageLength": 10,	 
	} );  

    modal_add_media.columns().every( function () {
        var that = this;
 
        $( 'input', this.header() ).on( 'keyup change', function () {
            if ( that.search() !== this.value ) {
                that
                    .search( this.value )
                    .draw();
            }
        } );
    } );

}
