/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {
    var table=$('#externalapps').DataTable( {
        "ajax": {
            "url": "/admin/table/secrets",
            "dataSrc": "",
            "type" : "POST",
            "data": function(d){return JSON.stringify({})}
        },
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "columns": [
            { "data": "id"},
            { "data": "secret"},
            { "data": "description"},
            { "data": "role_id"},
            { "data": "category_id"},
            { "data": "domain"},
        ]
    } );
});

