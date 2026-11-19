var derivates_table =''
function setDomainHotplug(id){
    hotplug_table=$("#table-hotplug-"+id).DataTable({
        "ajax": {
            "url": "/api/v4/admin/item/desktop/" + encodeURIComponent(id) + "/media-list",
            "contentType": "application/json",
            "type": 'GET'
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "deferRender": true,
        "columns": [
            { "data": "name", "render": $.fn.dataTable.render.text()},
            { "data": "kind", "render": $.fn.dataTable.render.text()},
            { "data": "size", "render": $.fn.dataTable.render.text()}
        ],
        "order": [[0, 'desc']],
    });
}
