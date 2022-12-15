/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {

    booking_scheduler_table=$('#table-booking-scheduler').DataTable({
        "ajax": {
            "url": "/admin/table/scheduler_jobs",
            "data": function(d){return JSON.stringify({'order_by':'date','pluck':['id','name','kind','next_run_time','kwargs'],'id':'bookings','index':'type'})},
            "contentType": "application/json",
            "type": 'POST',
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "bLengthChange": false,
        "bFilter": false,
        "rowId": "id",
        "deferRender": true,
        "columns": [
            { "data": "name"},
            { "data": "kind"},
            { "data": "next_run_time"},
            { "data": "kwargs"},
            // {
            // "className":      'actions-control',
            // "orderable":      false,
            // "data":           null,
            // "width": "58px",
            // "defaultContent": '<button id="btn-scheduler-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button>'
            // },
            ],
         "order": [[2, 'asc']],
         "columnDefs": [ {
                        "targets": 2,
                        "render": function ( data, type, full, meta ) {
                          return moment.unix(full.next_run_time);
                        }},
                        {
                        "targets": 3,
                        "render": function ( data, type, full, meta ) {
                            return JSON.stringify(full.kwargs);
                        }}]
        } )
    $.getScript("/isard-admin/static/admin/js/socketio.js")
});
