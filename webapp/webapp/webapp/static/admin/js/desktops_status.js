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


interval=1000;
echart_objects = {};

$(document).ready(function() {
    // Trigger function each interval seconds
    update();
});

function update() {
    $.ajax({
        url: "/api/v3/stats/desktops/status",
        type: "GET",
        contentType: 'application/json',
        beforeSend: function() {
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
                if (! statuses.hasOwnProperty(value)){
                    $("#card_"+value).remove();
                    delete echart_objects[value];
                }
            });
            $.each(statuses, function (key, value) {
                if (! echart_objects.hasOwnProperty(key)){
                    $("#statuses").append(chart_html(key));
                    echart_objects[key] = {"obj":$("#echart_history_"+key).echartHistory([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], key,200,200),"data":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]};
                    var el = document.getElementById("card_"+key)
                    el.addEventListener('click', e=>{
                        $('.echart-card').removeClass('echart-clicked');
                        $("#card_"+key).addClass('echart-clicked');
                        $('.echart-card-select').hide();
                        $("#select_"+key).show();
                        initialize_table(key);
                    });
                }else{
                    update_history_echart(key,echart_objects[key], value);
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

function chart_html(id) {
    var echart_template = '<article id="card_'+id+'" data-status="'+id+'" class="col-md-2 echart-card"><div class="well"><div id="echart_history_'+id+'"></div><div class="row"><select class="form-control echart-card-select" id="select_'+id+'" style="display:none"><option value="" selected>Actions</option>'
    switch (id) {
        case "Stopped":
            echart_template += '<option value="stopped">Stopped</option><option value="starting">Starting</option><option value="running">Running</option><option value="stopping">Stopping</option><option value="error">Error</option>'
            break;
        case "Starting":
            echart_template += '<option value="stopped">Stopped</option><option value="starting">Starting</option><option value="running">Running</option><option value="stopping">Stopping</option><option value="error">Error</option>'
            break;
        case "Started":
            echart_template += '<option value="stopped">Stopped</option><option value="starting">Starting</option><option value="running">Running</option><option value="stopping">Stopping</option><option value="error">Error</option>'
            break;
    }
    echart_template += '</select></div></div></article>'
    return echart_template
}

function update_history_echart(chart_id,chart,newdata) {
    if (chart["data"].length > 30) {
        chart["data"].shift();
    }else{
        // chart["data"] = [5,0,5,0,5,0,5,0,5,0]
    }
    chart["data"].push(newdata);

    chart["obj"].setOption({
        title: {
            text: chart_id+": "+newdata,
            left: 'center'
        },
        series: [
            {
            data: chart["data"]
            }
        ]
    });
}


function initialize_table(status){
    if ( $.fn.dataTable.isDataTable( '#domains' ) ) {
        $('#domains').DataTable().ajax.url("/api/v3/admin/domains_status/"+status).load();
    }
    $("#domains").DataTable({
        ajax: {
        url: "/api/v3/admin/domains_status/"+status,
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
            { "data": "id"},
            { "data": "name" },
            { "data": "accessed", 'defaultContent': '' },
            { "data": "status", visible: false },
        ],
        order: [[ 2, "desc" ]],
        columnDefs: [{
                "targets": 2,
                "render": function (data, type, full, meta) {
                    if ( type === 'display' || type === 'filter' ) {
                        return moment.unix(full.accessed).fromNow()
                    }
                    return full.accessed
                }
            }
        ],
    },
);
}