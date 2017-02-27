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
        console.log($(this).attr('id'),data);
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
