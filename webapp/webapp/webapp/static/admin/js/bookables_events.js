/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function () {

    p_detail_table = "";
    b_detail_table = "";

    // PLANNING

    planning_table = $('#table-planning').DataTable({
        "ajax": {
            "type": "GET",
            "url": "/api/v3/admin/reservables_planner",
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "deferRender": true,
        "columns": [
            {
                "data": null, "defaultContent": '<button title="See bookings in this plan" class="btn btn-xs btn-info" type="button" data-placement="top"><i class="fa fa-plus"></i></button>',
                "orderable": false, "className": 'details-control',
            },
            {
                "data": "start", "render": function (data, type, full, meta) {
                    const date = new Date(data);
                    if (type === 'display' || type === 'filter') {
                        return moment(date).format("DD-MM-YY HH:mm");
                    }
                    return date;
                }
            },
            {
                "data": "end", "render": function (data, type, full, meta) {
                    const date = new Date(data);
                    if (type === 'display' || type === 'filter') {
                        return moment(date).format("DD-MM-YY HH:mm");
                    }
                    return date;
                }
            },
            { "data": "subitem_id" },
            { "data": "item" },
            { "data": "units", "defaultContent": 0, "width": "60px" },
            { "data": "bookings", "defaultContent": 0 },
            {
                "data": null, "orderable": false, "render": function (data, type, full, meta) {
                    return `<button class="btn btn-xs btn-warning" type="button" title="Remove all bookings inside this plan" id="btn-empty" data-placement="top" ><i class="fa fa-circle-o"></i> Empty</button>
                            <button class="btn btn-xs btn-danger" type="button" id="btn-delete-plan" data-placement="top" ><i class="fa fa-trash"></i> Delete</button>`;
                }
            },
            { "data": "id", "visible": false },
        ],
        "order": [[1, 'asc']],
    });

    $detailPlanning = $("#planning-detail");
    adminShowIdCol(planning_table);
    addDateRangePicker($("#table-planning-filters .date-filters input"), "table-planning")

    $('#table-planning').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        if (p_detail_table) {
            p_detail_table.destroy();
        }
        var row = planning_table.row(tr);
        planId = row.data().id

        if (row.child.isShown()) {
            // This row is already open - close it
            opened_row = null;
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            // Open this row
            opened_row = row
            row.child(addPlanningDetailPannel(row.data())).show();
            renderPlanningDetailDatatable(planId);
            $("#planning-detail .clear-date").on("click", function () {
                $(this).prev("input").val('');
                filterDateDatatable("table-p-detail");
            })
            // Close other rows
            if (planning_table.row('.shown').length) {
                $('.details-control', planning_table.row('.shown').node()).click();
            }
            tr.addClass('shown');
        }
    });

    $('#table-planning').find(' tbody').on('click', 'button', function () {
        var data = $(this).closest("table").DataTable().row($(this).parents('tr')).data();
        if ($(this).attr('id') == 'btn-empty') {
            new PNotify({
                title: `Empty plan`,
                text: `Are you sure you want to clear all the bookings in this plan?`,
                hide: false,
                opacity: 0.9,
                confirm: { confirm: true },
                buttons: { closer: false, sticker: false },
                history: { history: false },
            }).get().on('pnotify.confirm', function () {
                $.ajax({
                    type: 'DELETE',
                    url: `/api/v3/admin/booking/empty/${data.id}`,
                    accept: "application/json",
                    success: function (resp) {
                        new PNotify({
                            title: 'Deleted',
                            text: `Plan emptied successfully`,
                            hide: true,
                            delay: 2000,
                            opacity: 1,
                            type: 'success'
                        });
                        planning_table.ajax.reload();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR emptying plan`,
                            text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        });
                    }
                });
            });
        } else if ($(this).attr('id') == 'btn-delete-plan') {
            new PNotify({
                title: `Delete plan`,
                text: `Are you sure you want to delete this plan?`,
                hide: false,
                opacity: 0.9,
                confirm: { confirm: true },
                buttons: { closer: false, sticker: false },
                history: { history: false },
            }).get().on('pnotify.confirm', function () {
                $.ajax({
                    type: 'DELETE',
                    url: `/api/v3/admin/reservables_planner/${data.id}`,
                    accept: "application/json",
                    success: function (resp) {
                        new PNotify({
                            title: 'Deleted',
                            text: `Plan deleted successfully`,
                            hide: true,
                            delay: 2000,
                            opacity: 1,
                            type: 'success'
                        });
                        planning_table.ajax.reload();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR deleting plan`,
                            text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        });
                    }
                });
            });
        } else if ($(this).attr('id') == 'btn-delete-booking') {
            new PNotify({
                title: `Delete booking`,
                text: `Are you sure you want to delete this booking?`,
                hide: false,
                opacity: 0.9,
                confirm: { confirm: true },
                buttons: { closer: false, sticker: false },
                history: { history: false },
            }).get().on('pnotify.confirm', function () {
                $.ajax({
                    type: 'DELETE',
                    url: `/api/v3/booking/event/${data.id}`,
                    accept: "application/json",
                    success: function (resp) {
                        new PNotify({
                            title: 'Deleted',
                            text: `Booking deleted successfully`,
                            hide: true,
                            delay: 2000,
                            opacity: 1,
                            type: 'success'
                        });
                        booking_table.ajax.reload();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR deleting booking`,
                            text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        });
                    }
                });
            });
        };
    });

    // BOOKINGS

    booking_table = $('#table-booking').DataTable({
        "ajax": {
            "type": "GET",
            "url": "/api/v3/bookings",
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "deferRender": true,
        "columns": [
            {
                "data": null, "defaultContent": '<button title="See plans with this booking" class="btn btn-xs btn-info" type="button" data-placement="top"><i class="fa fa-plus"></i></button>',
                "orderable": false, "className": 'details-control',
            },
            {
                "data": "start", "render": function (data, type, full, meta) {
                    const date = new Date(data);
                    if (type === 'display' || type === 'filter') {
                        return moment(date).format("DD-MM-YY HH:mm");
                    }
                    return date;
                }
            },
            {
                "data": "end", "render": function (data, type, full, meta) {
                    const date = new Date(data);
                    if (type === 'display' || type === 'filter') {
                        return moment(date).format("DD-MM-YY HH:mm");
                    }
                    return date;
                }
            },
            { "data": "title" },
            { "data": "username" },
            { "data": "category" },
            { "data": "item_type" },
            { "data": "units" },
            {
                "data": "plans", "render": function (data, type, full, meta) {
                    return data.length;
                }
            },
            {
                "data": null, "orderable": false, "render": function (data, type, full, meta) {
                    return `<button class="btn btn-xs btn-danger" id="btn-delete-booking" type="button"  data-placement="top" ><i class="fa fa-trash"></i> Delete</button>`;
                }
            },
            { "data": "id", "visible": false }

        ],
        "order": [[1, 'asc']],
    });

    $detailBooking = $("#booking-detail");
    adminShowIdCol(booking_table);
    addDateRangePicker($("#table-booking-filters .date-filters input"), "table-booking")

    $('#table-booking').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        if (b_detail_table) {
            b_detail_table.destroy();
        }
        var row = booking_table.row(tr);
        bookingId = row.data().id

        if (row.child.isShown()) {
            // This row is already open - close it
            opened_row = null;
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            // Open this row
            opened_row = row
            row.child(addBookingDetailPannel(row.data())).show();
            renderBookingDetailDatatable(bookingId);

            // Close other rows
            if (booking_table.row('.shown').length) {
                $('.details-control', booking_table.row('.shown').node()).click();
            }
            tr.addClass('shown');
        }
    });

    $('#table-booking').find(' tbody').on('click', 'button', function () {
        var data = $(this).closest("table").DataTable().row($(this).parents('tr')).data();
        if ($(this).attr('id') == 'btn-delete-booking') {
            new PNotify({
                title: `Delete booking`,
                text: `Are you sure you want to delete this booking?`,
                hide: false,
                opacity: 0.9,
                confirm: { confirm: true },
                buttons: { closer: false, sticker: false },
                history: { history: false },
            }).get().on('pnotify.confirm', function () {
                $.ajax({
                    type: 'DELETE',
                    url: `/api/v3/booking/event/${data.id}`,
                    accept: "application/json",
                    success: function (resp) {
                        new PNotify({
                            title: 'Deleted',
                            text: `Booking deleted successfully`,
                            hide: true,
                            delay: 2000,
                            opacity: 1,
                            type: 'success'
                        });
                        booking_table.ajax.reload();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR deleting booking`,
                            text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        });
                    }
                });
            });
        };
    });


    // SCHEDULER

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
            { "data": "name" },
            { "data": "kind" },
            { "data": "next_run_time" },
            { "data": "kwargs" }
        ],
        "order": [[2, 'asc']],
        "columnDefs": [{
            "targets": 2,
            "render": function (data, type, full, meta) {
                return moment.unix(full.next_run_time);
            }
        },
        {
            "targets": 3,
            "render": function (data, type, full, meta) {
                return JSON.stringify(full.kwargs);
                        }}]
        } )


    $(".clear-date").on("click", function () {
        $(this).prev("input").val('');
        filterDateDatatable("table-planning");
        filterDateDatatable("table-booking");
    })

    $.getScript("/isard-admin/static/admin/js/socketio.js")
});


function addPlanningDetailPannel(d) {
    $newPanel = $detailPlanning.clone();
    $newPanel.html(function (i, oldHtml) {
        return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name);
    });
    return $newPanel
}

function renderPlanningDetailDatatable(planId) {
    p_detail_table = $('#table-p-detail').DataTable({
        "ajax": {
            "type": "GET",
            "url": `/api/v3/admin/reservables_planner/${planId}/bookings`,
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "bLengthChange": false,
        "rowId": "id",
        "deferRender": true,
        "columns": [
            {
                "data": "start", "render": function (data, type, full, meta) {
                    const date = new Date(data);
                    if (type === 'display' || type === 'filter') {
                        return moment(date).format("DD-MM-YY HH:mm");
                    }
                    return date;
                }
            },
            {
                "data": "end", "render": function (data, type, full, meta) {
                    const date = new Date(data);
                    if (type === 'display' || type === 'filter') {
                        return moment(date).format("DD-MM-YY HH:mm");
                    }
                    return date;
                }
            },
            { "data": "title" },
            { "data": "username" },
            { "data": "category" },
            { "data": "item_type" },
            { "data": "units" },
            {
                "data": null, "orderable": false, "render": function (data, type, full, meta) {
                    return `<button class="btn btn-xs btn-danger" id="btn-delete-booking" type="button"  data-placement="top" ><i class="fa fa-trash"></i> Delete</button>`;
                }
            }

        ],
        "initComplete": function () {
            addDateRangePicker($("#planning-detail .date-filters input"), "table-p-detail");
            $('#table-p-detail tr td').on("click", function (t) {
                if ($(t.target).attr('type')!="button") {
                    var id = $(this).parents('tr').attr("id");
                    $("#table-booking_filter input").val(id);
                    window.scrollTo(0, $("#booking-panel").offset().top);
                    $("#table-booking_filter input").trigger('input');
                }
            });
        },
        "order": [[0, 'asc']],
    });
    $.fn.dataTable.ext.search.pop();
}


function addBookingDetailPannel(d) {
    $newPanel = $detailBooking.clone();
    $newPanel.html(function (i, oldHtml) {
        return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name);
    });
    return $newPanel
}

function renderBookingDetailDatatable(bookingId) {
    b_detail_table = $('#table-b-detail').DataTable({
        "ajax": {
            "type": "GET",
            "url": `/api/v3/admin/booking/${bookingId}/plans`
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "bLengthChange": false,
        "rowId": "id",
        "deferRender": true,
        "columns": [
            {
                "data": "start", "render": function (data, type, full, meta) {
                    const date = new Date(data);
                    if (type === 'display' || type === 'filter') {
                        return moment(date).format("DD-MM-YY HH:mm");
                    }
                    return date;
                }
            },
            {
                "data": "end", "render": function (data, type, full, meta) {
                    const date = new Date(data);
                    if (type === 'display' || type === 'filter') {
                        return moment(date).format("DD-MM-YY HH:mm");
                    }
                    return date;
                }
            },
            { "data": "subitem_id" },
            { "data": "item" },
            { "data": "units" },
            { "data": "id", "visible": false }
        ],
        "initComplete": function () {
            adminShowIdCol(b_detail_table);
            $('#table-b-detail tr td').on("click", function () {
                var id = $(this).parents('tr').attr("id");
                $("#table-planning_filter input").val(id);
                window.scrollTo(0, $("#planning-panel").offset().top);
                $("#table-planning_filter input").trigger('input');
            });
        },
        "order": [[0, 'asc']],
    });
    $.fn.dataTable.ext.search.pop();
}


function addDateRangePicker(input, table) {
    input.daterangepicker({
        singleDatePicker: true,
        showDropdowns: true,
        minYear: parseInt(moment().format('YYYY')) - 2,
        maxYear: parseInt(moment().format('YYYY')) + 2,
        locale: {
            format: 'DD-MM-YYYY'
        }
    }, function (start, end, label) {
    });
    input.val('');
    input.on('apply.daterangepicker', function (ev, picker) {
        filterDateDatatable(table);
    });
}

function filterDateDatatable(table) {
    var startMin = moment($(`#${table}-filters #start-min`).val(), "DD-MM-YYYY").startOf('day');
    var endMax = moment($(`#${table}-filters #end-max`).val(), "DD-MM-YYYY").endOf('day');
    $.fn.dataTable.ext.search.pop();
    filter =
        function (settings, data, dataIndex) {
            var start = {}
            var end = {}
            if (["table-planning", "table-booking"].includes(table)) {
                var start = moment(data[1], "DD-MM-YYYY HH:mm");
                var end = moment(data[2], "DD-MM-YYYY HH:mm");
            } else if (table == "table-p-detail") {
                var start = moment(data[0], "DD-MM-YYYY HH:mm");
                var end = moment(data[1], "DD-MM-YYYY HH:mm");
            }
            if (startMin._isValid && endMax._isValid) {
                return (
                    ((start.isSameOrAfter(startMin) && start.isSameOrBefore(endMax)) ||
                    (end.isSameOrAfter(startMin) && end.isSameOrBefore(endMax)) ||
                    (start.isSameOrBefore(startMin) && end.isSameOrAfter(endMax)))
                );
            } else if (!startMin._isValid && endMax._isValid) {
                return (end.isSameOrAfter(endMax) && start.isSameOrBefore(endMax) ||
                    end.isSameOrBefore(endMax));
            } else if (startMin._isValid && !endMax._isValid) {
                return (start.isSameOrBefore(startMin) && end.isSameOrAfter(startMin) ||
                    start.isSameOrAfter(startMin));
            } else {
                return true;
            }
        }
    $.fn.dataTable.ext.search.push(filter);
    $(`#${table}`).DataTable().draw();
}
