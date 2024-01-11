/*
 *   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
 *   Copyright (C) 2023 Josep Maria Viñolas Auquer
 *
 *   This program is free software: you can redistribute it and/or modify
 *   it under the terms of the GNU Affero General Public License as published by
 *   the Free Software Foundation, either version 3 of the License, or
 *   (at your option) any later version.
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *   GNU Affero General Public License for more details.
 *
 *   You should have received a copy of the GNU Affero General Public License
 *   along with this program.  If not, see <https://www.gnu.org/licenses/>.
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */


interval = 5000;
echart_objects = {};

$(document).ready(function () {
    // Trigger function each interval seconds
    $("#change-interval").val(interval);
    update();
});


function update() {
    $.ajax({
        url: "/api/v3/stats/desktops/status",
        type: "GET",
        contentType: 'application/json',
        beforeSend: function () {
            start_ts = new Date().getTime();
        },
        success: function (data) {
            var end_ts = new Date().getTime();
            query_seconds = (end_ts - start_ts) / 1000
            $('#time').html(query_seconds);
            // Adapt to database response time
            // interval = query_seconds + 5000;
            total = data.total;
            statuses = data.status;
            $('#total').html(total);

            actual_statuses = Object.keys(echart_objects);
            $.each(actual_statuses, function (key, value) {
                // if any status is not in the response, remove it
                if (!statuses.hasOwnProperty(value)) {
                    $("#card_" + value).remove();
                    delete echart_objects[value];
                }
            });
            $.each(statuses, function (key, value) {
                if (!echart_objects.hasOwnProperty(key)) {
                    $("#statuses").append(chart_html(key));
                    var chart_height = 210;
                    var chart_width = parseInt($("#echart_history_" + key).width());

                    echart_objects[key] = { "obj": $("#echart_history_" + key).echartHistory([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], key, chart_width, chart_height), "data": ['-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', '-', value, value] };
                    option = echart_objects[key].obj.getOption();
                    option.xAxis[0].axisLabel.show = false
                    option.yAxis[0].axisLabel.inside = true
                    option.yAxis[0].axisLabel.margin = -15
                    option.yAxis[0].min = value/2
                    echart_objects[key].obj.setOption(option);
                    var el = document.getElementById("card_" + key)
                    el.addEventListener('click', e => {
                        $('.show-datatable-checkbox').show();
                        $('.echart-card').removeClass('echart-clicked');
                        $("#card_" + key).addClass('echart-clicked');
                        $('.echart-card-select').hide();
                        $("#select_" + key).show();
                        if ($('#show-datatable').iCheck('update')[0].checked) {
                            initialize_table(key);
                        }
                        $('.echart-card select').unbind();
                        $('.echart-card select').on('change', function () {
                            changeStatus($(this).closest('article').data("status"), $(this).val(), $(this));
                        });
                    });
                    update_history_echart(key, echart_objects[key], value);
                } else {
                    update_history_echart(key, echart_objects[key], value);
                }
            });
        },
        error: function (xhr, ajaxOptions, thrownError) {
            console.log(xhr.status);
            console.log(thrownError);
        }
    });

    setTimeout(update, interval);
}

$('#show-datatable').on('ifChecked', function (event) {
    var key = $("#statuses .echart-clicked").data("status");
    initialize_table(key);
    $("#table-panel").show();
});
$('#show-datatable').on('ifUnchecked', function (event) {
    $("#table-panel").hide();
});


$("#change-interval").on('change', function () {
    interval = parseInt($("#change-interval").val());
    new PNotify({
        title: `Query interval changed to ${interval / 1000} seconds`,
        hide: true,
        delay: 2000,
        opacity: 1,
        type: 'success'
    })
});


function stopDesktop(domain_id, tr) {
    $.ajax({
        url: "/api/v3/desktop/stop/" + domain_id,
        type: "GET",
        success: function (data) {
            new PNotify({
                title: 'Stopping desktop...',
                hide: true,
                delay: 2000,
                opacity: 1,
                type: 'info'
            })
            $('#domains').DataTable().row(tr).remove().draw();
        },
        error: function ({ responseJSON: { description } = {} }) {
            const msg = description ? description : 'Something went wrong';
            new PNotify({
                title: 'ERROR stopping desktop',
                text: msg,
                hide: true,
                delay: 2000,
                opacity: 1,
                type: 'error'
            })
        }
    })
};


function changeStatus(currentStatus, targetStatus, select) {
    new PNotify({
        title: 'Are you sure?',
        text: `Are you sure you want to change all ${currentStatus} desktops to ${targetStatus}?`,
        hide: false,
        type: 'warning',
        confirm: {
            confirm: true
        }
    }).get().on(
        'pnotify.confirm',
        function () {
            $.ajax({
                url: `/api/v3/desktops/${currentStatus}/${targetStatus}`,
                type: "PUT",
                contentType: 'application/json',
                success: function (data) {
                    new PNotify({
                        title: 'Status changed succesfully',
                        text: `All ${currentStatus} desktops are now ${targetStatus}`,
                        hide: true,
                        delay: 2000,
                        opacity: 1,
                        type: 'success'
                    })
                    if (select) { select.val("placeholder"); }

                },
                error: function ({ responseJSON: { description } = {} }) {
                    const msg = description ? description : 'Something went wrong';
                    new PNotify({
                        title: 'ERROR changing status',
                        text: msg,
                        hide: true,
                        delay: 2000,
                        opacity: 1,
                        type: 'error'
                    })
                }
            })
        }
    ).on('pnotify.cancel', function () {
        if (select) { select.val("placeholder"); }
    })
}


function chart_html(id) {
    var options = ""
    var style = ""
    switch (id) {
        case "Stopped":
            options = `<option value="StartingPaused">Start-Pause</option>`
            break;
        case "Started":
            options = `<option value="Shutting-down">Soft shut down</option>
                                <option value="Stopping">Force shut down</option>`
            // <option value="">Stop by desktop priority</option>
            break;
        case "Failed":
            options = `<option value="StartingPaused">Start-Pause</option>`
            break;
        case "Downloading":
            options = `<option selected disabled>No actions available</option>`
            break;
        case "Shutting-down":
            options = `<option value="Stopping">Force Stop</option>`
            break;
    }
    if (!["Started", "Stopped", "Downloading", "Failed", "Shutting-down"].includes(id)) {
        options += `<option value="Failed">Force Failed</option>`
    }
    if (!["Started", "Stopped", "Starting", "Shutting-down", "Stopping"].includes(id)) {
        style = "style='background-color:mistyrose;'"
    }
    echart_template = `<article id="card_${id}" data-status="${id}"
                        class="col-xs-12 col-sm-4 col-md-4 col-lg-2 col-xl-1 echart-card"
                        >
                            <div class="well drop-shadow" ${style}><div id="echart_history_${id}" class="canvas_wrapper">
                            </div><div class="row" style="margin-top:-20px;">
                                <select class="form-control echart-card-select" id="select_${id}" style="display:none">
                                        <option disabled value="placeholder" selected>Actions</option>
                                        ${options}
                                </select>
                            </div></div>
                        </article>`

    return echart_template
}

function update_history_echart(chart_id, chart, newdata) {
    if (chart["data"].length > 30) {
        chart["data"].shift();

    } else {
        // chart["data"] = [5, 0, 5, 0, 5, 0, 5, 0, 5, 0]
    }
    chart["data"].push(newdata);

    chart["obj"].setOption({
        title: {
            text: chart_id.substring(0, 16) + ": " + newdata,
            left: 'center'
        },
        series: [
            {
                data: chart["data"]
            }
        ]
    });
}

$(window).on('resize', function(){
    var chart_width = parseInt($(".well .canvas_wrapper").width()-10);
    var chart_height = 210
    $.each(echart_objects, function(key, chart) {
        chart["obj"].resize({
            width: chart_width,
            height: chart_height
        });
    });
})


function initialize_table(status) {
    if ($.fn.dataTable.isDataTable('#domains')) {
        $('#domains').DataTable().ajax.url("/api/v3/admin/domains_status/" + status).load();
        $('#domains').DataTable().one('draw', function () {
            if (status == "Started") {
                $(".btn-stop").show();
            } else {
                $(".btn-stop").hide();
            }
        });
    } else {
        $("#domains").DataTable({
            ajax: {
                url: "/api/v3/admin/domains_status/" + status,
                type: "GET",
                contentType: 'application/json',
            },
            "sAjaxDataProp": "",
            "language": {
                "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
            },
            "rowId": "id",
            "deferRender": true,
            columns: [
                { "data": "id" },
                { "data": "name" },
                {
                    "orderable": false,
                    "data": null,
                    "title": "Action",
                    "width": "100px",
                    "render": function () {
                        let visible = status == "Started" ? "block" : "none"
                        return `<button type="button" class="btn btn-stop btn-pill-left btn-danger btn-xs" style="display:${visible};"><i class="fa fa-stop"></i> Stop</button>`;
                    }
                },
                {
                    "data": "accessed", 'defaultContent': '', 'render': function (data, type, row) {
                        if (type === 'display' || type === 'filter') {
                            return moment.unix(data).fromNow()
                        }
                        return data
                    },
                },
                { "data": "status", visible: false },
            ],
            initComplete: function () {
                $('#domains').on('click', '.btn-stop', function () {
                    var rowIndex = $(this).closest('tr').index();
                    var rowData = $("#domains").DataTable().row(rowIndex).data();
                    var tr = $(this).closest('tr');
                    stopDesktop(rowData.id, tr);
                });
            },
            order: [[2, "desc"]],
            columnDefs: [{
                "targets": 2,
                "render": function (data, type, full, meta) {
                    if (type === 'display' || type === 'filter') {
                        return moment.unix(full.accessed).fromNow()
                    }
                    return full.accessed
                }
            }],
        },
        );
    }
}