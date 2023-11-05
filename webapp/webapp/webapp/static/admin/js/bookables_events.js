/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {

    booking_scheduler_table=$('#table-booking-scheduler').DataTable({
        "ajax": {
            "type": "GET",
            "url": "/api/v3/admin/scheduler/jobs/bookings",
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
