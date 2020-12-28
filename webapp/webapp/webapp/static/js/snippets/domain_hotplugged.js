var derivates_table =''
function setDomainHotplug(id,hardware){

    hotplug_table=$("#table-hotplug-"+id).DataTable({
			"ajax": {
				"url": "/isard-admin/domain/media_list",
                "contentType": "application/json",
                "type": 'POST',
                "data": function(d){return JSON.stringify({'pk':id})}
			},
            "sAjaxDataProp": "",
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
			"deferRender": true,
			"columns": [
				{ "data": "name"},
				{ "data": "kind"},
                {'data':'size'}
                ],
			 "order": [[0, 'desc']],
    } );


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

