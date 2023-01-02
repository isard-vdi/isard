var derivates_table =''
function setDomainHotplug(id,hardware){
    hotplug_table=$("#table-hotplug-"+id).DataTable({
        "ajax": {
            "url": "/api/v3/desktops/media_list",
            "contentType": "application/json",
            "type": 'POST',
            "data": function(d){return JSON.stringify({'id':id})}
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
            { "data": "size"}
        ],
        "order": [[0, 'desc']],
    });
}
