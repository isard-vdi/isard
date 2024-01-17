/*
*   Copyright © 2024 Naomi Hidalgo
*
*   This file is part of IsardVDI.
*
*   IsardVDI is free software: you can redistribute it and/or modify
*   it under the terms of the GNU Affero General Public License as published by
*   the Free Software Foundation, either version 3 of the License, or (at your
*   option) any later version.
*
*   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
*   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
*   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
*   details.
*
*   You should have received a copy of the GNU Affero General Public License
*   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
*
* SPDX-License-Identifier: AGPL-3.0-or-later
*/

$(document).ready(function () {

    // Scheduler
    scheduler_table = $('#table-scheduler').DataTable({
        "ajax": {
            "type": "GET",
            "url": "/api/v3/admin/scheduler/jobs/system",
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
            {
                "className": 'actions-control',
                "orderable": false,
                "data": null,
                "width": "58px",
                "defaultContent": '<button id="btn-scheduler-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button>'
            },
        ],
        "order": [[2, 'asc']],
        "columnDefs": [{
            "targets": 2,
            "render": function (data, type, full, meta) {
                return moment.unix(full.next_run_time);
            }
        }]
    });


    $('#table-scheduler').find(' tbody').on('click', 'button', function () {
        var data = scheduler_table.row($(this).parents('tr')).data();
        if ($(this).attr('id') == 'btn-scheduler-delete') {
            new PNotify({
                title: 'Delete scheduled task',
                text: "Do you really want to delete scheduled task " + moment.unix(data.next_run_time) + "?",
                hide: false,
                opacity: 0.9,
                confirm: { confirm: true },
                buttons: { closer: false, sticker: false },
                history: { history: false },
                addclass: 'pnotify-center'
            }).get().on('pnotify.confirm', function () {
                $.ajax({
                    type: 'DELETE',
                    url: '/scheduler/' + data["id"],
                    accept: "application/json",
                }).done(function (resp) {
                    scheduler_table.row('#' + data["id"]).remove().draw();
                });
            }).on('pnotify.cancel', function () {
            });
        }
    });


    $('.btn-scheduler').on('click', function () {
        $('#modalScheduler').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        scheduler_init();
    });


    $("#modalScheduler #send").on('click', function (e) {
        const formData = $('#modalAddScheduler').serializeObject();
        let url = '';
        let data = {
            kwargs: {}
        }
        // For once at a date jobs we must parse the selected datetime as utc and call another endpoint
        if (formData['kind'] == 'date') {
            url = '/scheduler/advanced/date/system/' + formData['action']
            data["date"] = moment(formData['daterangepicker_start'], "DD/MM/YYYY HH:mm").utc().format('YYYY-MM-DDTHH:mmZ')
        } else {
            const hour = formData['kind'] == 'cron' ? moment(formData["hour"], "HH").utc().format('HH') : formData["hour"]
            url = '/scheduler/system/' + formData["kind"] + "/" + formData["action"] + "/" + hour + "/" + formData["minute"]
            // If we are adding a cron job we must schedule it as utc, if its an interval we keep the introduced hour as is
        }
        // If the action has kwargs we must add it to the data to be sent
        if ($('.kwargs_field').length > 0) {
            $('.kwargs_field').each(function () {
                data['kwargs'][this.id] = this.value;
            });
        }
        $.ajax({
            type: 'POST',
            url: url,
            data: JSON.stringify(data),
            contentType: "application/json",
            accept: "application/json",
        }).done(function (data) { scheduler_table.ajax.reload(); });
        $("#modalAddScheduler")[0].reset();
        $("#modalScheduler").modal('hide');
    });

    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on);

});

function socketio_on() { }

function scheduler_init() {
    $("#modalScheduler #modalAddScheduler").each(function () {
        this.reset();
    });

    $.ajax({
        type: 'GET',
        url: '/scheduler/actions',
        accept: "application/json",
    }).done(function (response) {
        response.forEach(function (action) {
            $("#modalScheduler #action").append(
                "<option value=" + action.id + ">" + action.name + "</option>"
            );
        })
        $("#modalScheduler #action option[value='recycle_bin_delete_admin']").remove();
        $("#modalScheduler #action option[value='recycle_bin_delete']").remove();
    });

    $('#modalAddScheduler #kind').on('change', function (e) {
        var valueSelected = this.value;
        if (valueSelected == 'cron' || valueSelected == 'interval') {
            $('#modalAddScheduler #div_interval_cron').show();
            $('#modalAddScheduler #div_date').hide();
        } else if (valueSelected == 'date') {
            $('#modalAddScheduler #div_date').show();
            $('#modalAddScheduler #div_date #datePicker').daterangepicker({
                parentEl: "#modalAddScheduler #div_date",
                singleDatePicker: true,
                singleClasses: "picker_2",
                timePicker: true,
                locale: {
                    format: 'DD/MM/YYYY HH:mm'
                }
            });
            $('#modalAddScheduler #div_interval_cron').hide();
        } else {
            $('#modalAddScheduler #div_interval_cron').hide();
            $('#modalAddScheduler #div_date').hide();
        }
    })

    $('#modalAddScheduler #action').on('change', function (e) {
        var selectedAction = this.value;
        var selectedActionText = this.options[this.selectedIndex].text;
        $.ajax({
            type: "GET",
            url: "/scheduler/action/" + selectedAction,
            accept: "application/json",
            success: function (data) {
                // If the action requires to introduce data
                if (data.length > 0) {
                    $('#actionTitle').html('<i class="fa fa-info-circle" aria-hidden="true"></i> ' + selectedActionText.charAt(0).toUpperCase() + selectedActionText.slice(1));function scheduler_init(){
                        $("#modalScheduler #modalAddScheduler").each(function () {
                            this.reset();
                          });
                    
                        $.ajax({
                            type: 'GET',
                            url: '/scheduler/actions',
                            accept: "application/json",
                        }).done(function(response) {
                            response.forEach(function(action) {
                                $("#modalScheduler #action").append(
                                  "<option value=" + action.id + ">" + action.name + "</option>"
                                );
                              })
                              $("#modalScheduler #action option[value='recycle_bin_delete_admin']").remove();
                              $("#modalScheduler #action option[value='recycle_bin_delete']").remove();
                        });
                    
                        $('#modalAddScheduler #kind').on('change', function (e) {
                            var valueSelected = this.value;
                            if(valueSelected == 'cron' || valueSelected == 'interval'){
                                $('#modalAddScheduler #div_interval_cron').show();
                                $('#modalAddScheduler #div_date').hide();
                            }else if(valueSelected == 'date'){
                                $('#modalAddScheduler #div_date').show();
                                $('#modalAddScheduler #div_date #datePicker').daterangepicker({
                                    parentEl: "#modalAddScheduler #div_date",
                                    singleDatePicker: true,
                                    singleClasses: "picker_2",
                                    timePicker: true,
                                    locale: {
                                        format: 'DD/MM/YYYY HH:mm'
                                    }
                                });
                                $('#modalAddScheduler #div_interval_cron').hide();
                            }else{
                                $('#modalAddScheduler #div_interval_cron').hide();
                                $('#modalAddScheduler #div_date').hide();
                            }
                        })
                    
                        $('#modalAddScheduler #action').on('change', function (e) {
                            var selectedAction = this.value;
                            var selectedActionText = this.options[this.selectedIndex].text;
                            $.ajax({
                                type: "GET",
                                url: "/scheduler/action/"+selectedAction,
                                accept: "application/json",
                                success: function(data)
                                {
                                    // If the action requires to introduce data
                                    if (data.length > 0) {
                                        $('#actionTitle').html('<i class="fa fa-info-circle" aria-hidden="true"></i> ' + selectedActionText.charAt(0).toUpperCase() + selectedActionText.slice(1))
                                        gen_form("#modalAddScheduler #div_action_form", data)
                                    } else {
                                        $("#modalAddScheduler #div_action_form, #actionTitle").html("")
                                    }
                                }
                            });
                        })
                    }
                    
                    gen_form("#modalAddScheduler #div_action_form", data);
                } else {
                    $("#modalAddScheduler #div_action_form, #actionTitle").html("");
                }
            }
        });
    })
}
