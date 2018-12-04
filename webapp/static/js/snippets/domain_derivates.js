var derivates_table =''
function setDomainDerivates(id){
	$("#bulk-edit-"+id).on( 'click', function () {
            $("#modalBulkEditForm")[0].reset();
            setHardwareOptions('#modalBulkEdit','disk');
			$('#modalBulkEdit').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            setHardwareDomainDefaults('#modalBulkEdit', id);
            //~ $('#modalAddFromBuilder #modalAdd').parsley();
            modal_bulk_edit_setdata("#modalBulkEditForm");
	});    
        
    derivates_table=$("#table-derivates-"+id).DataTable({
			"ajax": {
				"url": "/domains/derivates/",
                "contentType": "application/json",
                "type": 'POST',
                "data": function(d){return JSON.stringify({'pk':id})}
			},
            "sAjaxDataProp": "",
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
            //~ "bLengthChange": false,
            //~ "bFilter": false,
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{ "data": "name"},
				{ "data": "kind"},
                {'data':'user'},
				{'data':'category'},
                {'data': 'group'},
                ],
			 "order": [[0, 'desc']],
			 //~ "columnDefs": [ {
							//~ "targets": 0,
							//~ "render": function ( data, type, full, meta ) {
                              //~ if ( type === 'display' || type === 'filter' ) {
                                    //~ return moment.unix(full.when).fromNow();
                              //~ }                                 
                              //~ return data;  
							//~ }}]
    } );
            
			//~ api.ajax('/domain_derivates','POST',{'pk':id}).done(function(derivates) {
                //~ var wasted=0
                //~ $.each(derivates,function(index,val){
                    //~ $("#table-derivates-"+id).append('<tr><td>'+val['name']+'</td><td>'+val['kind']+'</td><td>'+val['user']+'</td></tr>');
                //~ });  
            //~ });

    $("#modalBulkEdit #send").on('click', function(e){
            var form = $('#modalBulkEditForm');
            //~ form.parsley().validate();
            //~ if (form.parsley().isValid()){
                    data=$('#modalBulkEditForm').serializeObject();
                    socket.emit('domain_bulkedit',data)
                    //~ console.log('is valid form')
            //~ }
        });
            
}
    
function modal_bulk_edit_setdata(id){
        names=''
        ids=[]
        $(id+" #ids").find('option').remove();
        if(derivates_table.rows('.active').data().length){
            $.each(derivates_table.rows('.active').data(),function(key, value){
                //~ names+=value['name']+'\n';
                //~ ids.push(value['id']);
                $(id+' #ids').append('<option value=' + value.id + '>' + value.name + '</option>');
            });
            //~ var text = "You are about to these desktops:\n\n "+names
        }else{ 
            $.each(derivates_table.rows({filter: 'applied'}).data(),function(key, value){
                //~ ids.push(value['id']);
                $(id+' #ids').append('<option value=' + value.id + '>' + value.name + '</option>');
            });
            //~ var text = "You are about to "+derivates_table.rows({filter: 'applied'}).data().length+" desktops!\n All the desktops in list!"
        }    
        $(id+' #ids > option').attr("selected",true);
        //~ console.log(text)
        //~ $(id+' #afecteds').val(text);
        
        $(id+" .btn-unselect-all").on( 'click', function () {
            $(id+' #ids > option').attr("selected",false);
        })


        $(id+" .btn-select-all").on( 'click', function () {
            $(id+' #ids > option').attr("selected",true);
        })        
    
}
