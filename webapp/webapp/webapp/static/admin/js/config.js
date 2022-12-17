/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {
    // Scheduler
    scheduler_table=$('#table-scheduler').DataTable({
        "ajax": {
            "url": "/admin/table/scheduler_jobs",
            "data": function(d){return JSON.stringify({'order_by':'date','pluck':['id','name','kind','next_run_time'],'id':'system','index':'type'})},
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
            {
            "className":      'actions-control',
            "orderable":      false,
            "data":           null,
            "width": "58px",
            "defaultContent": '<button id="btn-scheduler-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button>'
            },
            ],
         "order": [[1, 'asc']],
         "columnDefs": [ {
                        "targets": 2,
                        "render": function ( data, type, full, meta ) {
                          return moment.unix(full.next_run_time);
                        }}]
    } );

    $('#table-scheduler').find(' tbody').on( 'click', 'button', function () {
        var data = scheduler_table.row( $(this).parents('tr') ).data();
        if($(this).attr('id')=='btn-scheduler-delete'){
                new PNotify({
                        title: 'Delete scheduled task',
                            text: "Do you really want to delete scheduled task "+moment.unix(data.next_run_time)+"?",
                            hide: false,
                            opacity: 0.9,
                            confirm: {confirm: true},
                            buttons: {closer: false,sticker: false},
                            history: {history: false},
                            addclass: 'pnotify-center'
                        }).get().on('pnotify.confirm', function() {
                            api.ajax('/scheduler/'+data["id"],'DELETE',{}).done(function(data) {
                                // Websocket event will delete it
                                // scheduler_table.row('#'+data["id"]).remove().draw();
                            });
                        }).on('pnotify.cancel', function() {
                });
        }
    });

    $('.btn-scheduler').on( 'click', function () {
        $('#modalScheduler').modal({
                backdrop: 'static',
                keyboard: false
        }).modal('show');
        scheduler_init();
    });

    $("#modalScheduler #send").on('click', function(e){
            var form = $('#modalAddScheduler');
            const formData=$('#modalAddScheduler').serializeObject();
            let url = ''
            let data = {
                kwargs: {}
            }
            // For once at a date jobs we must parse the selected datetime as utc and call another endpoint
            if (formData['kind'] == 'date') {
                url = '/scheduler/advanced/date/system/' + formData['action']
                data["date"] = moment(formData['daterangepicker_start'], "DD/MM/YYYY HH:mm").utc().format('YYYY-MM-DDTHH:mmZ')
            } else {
                const hour = formData['kind'] == 'cron' ? moment(formData["hour"], "HH").utc().format('HH') : formData["hour"]
                url = '/scheduler/system/'+formData["kind"]+"/"+formData["action"]+"/"+ hour + "/"+ formData["minute"]
                // If we are adding a cron job we must schedule it as utc, if its an interval we keep the introduced hour as is
            }
            // If the action has kwargs we must add it to the data to be sent
            if ($('.kwargs_field').length > 0){
                $('.kwargs_field').each(function() {
                    data['kwargs'][this.id] = this.value
                });
            }
            $.ajax({
                type: 'POST',
                url: url,
                data: JSON.stringify(data),
                contentType: "application/json",

            }).done(function(data) {});
            $("#modalAddScheduler")[0].reset();
            $("#modalScheduler").modal('hide');
        });

    // Backups
    $('.btn-backup').on( 'click', function () {
        new PNotify({
                title: 'Create backup',
                    text: "Do you really want to create a new backup?",
                    hide: false,
                    opacity: 0.9,
                    confirm: {confirm: true},
                    buttons: {closer: false,sticker: false},
                    history: {history: false},
                    addclass: 'pnotify-center'
                }).get().on('pnotify.confirm', function() {
                    api.ajax('/api/v3/backup','POST',{}).done(function(data) {
                    });
                }).on('pnotify.cancel', function() {
        });
    });

    $('.btn-backups-upload').on( 'click', function () {
        $('#modalUpload').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
    });

    backups_table=$('#table-backups').DataTable({
            "ajax": {
                "url": "/api/v3/admin/table/backups",
                "contentType": "application/json",
                "type": 'POST',
                "data": function(d){return JSON.stringify({'order':'filename'})}
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
                { "data": "when"},
                { "data": "status"},
                { "data": "version", "defaultContent": "Unknown"},
                {
                "className":      'actions-control',
                "orderable":      false,
                "data":           null,
                "width": "88px",
                "defaultContent": '<button id="btn-backups-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button> \
                                   <button id="btn-backups-restore" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-sign-in" style="color:darkgreen"></i></button> \
                                   <button id="btn-backups-info" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-info" style="color:green"></i></button> \
                                   <button id="btn-backups-download" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-download" style="color:darkblue"></i></button>'
                },
                ],
             "order": [[0, 'desc']],
             "columnDefs": [ {
                            "targets": 0,
                            "render": function ( data, type, full, meta ) {
                              if ( type === 'display' || type === 'filter' ) {
                                    return moment.unix(full.when).fromNow();
                              }
                              return data;
                            }}]
    } );

     $('#table-backups').find(' tbody').on( 'click', 'button', function () {
        var data = backups_table.row( $(this).parents('tr') ).data();
        if($(this).attr('id')=='btn-backups-delete'){
            new PNotify({
                    title: 'Delete backup',
                        text: "Do you really want to delete backup on date "+moment.unix(data.when).fromNow()+"?",
                        hide: false,
                        opacity: 0.9,
                        confirm: {confirm: true},
                        buttons: {closer: false,sticker: false},
                        history: {history: false},
                        addclass: 'pnotify-center'
                    }).get().on('pnotify.confirm', function() {
                        api.ajax('/api/v3/backup/'+data["id"],'DELETE',{}).done(function(data) {
                        });
                    }).on('pnotify.cancel', function() {
            });
        }
        if($(this).attr('id')=='btn-backups-restore'){
            new PNotify({
                    title: 'Restore backup',
                        text: "Do you really want to restore backup from file "+data.filename+"? NOTE: After restoring isard-engine container MUST be restarted to apply db version upgrade!",
                        hide: false,
                        opacity: 0.9,
                        confirm: {confirm: true},
                        buttons: {closer: false,sticker: false},
                        history: {history: false},
                        addclass: 'pnotify-center'
                    }).get().on('pnotify.confirm', function() {
                        api.ajax('/api/v3/backup/restore/'+data["id"],'PUT',{}).done(function(data) {
                        });
                    }).on('pnotify.cancel', function() {
            });
        }
        if($(this).attr('id')=='btn-backups-download'){
            var url = '/api/v3/backup/download/'+data['id']+'?jwt='+localStorage.getItem("token");
            var anchor = document.createElement('a');
                anchor.setAttribute('href', url);
                anchor.setAttribute('download', data['filename']);
            var ev = document.createEvent("MouseEvents");
                ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
            anchor.dispatchEvent(ev);
        }
        if($(this).attr('id')=='btn-backups-info'){
            api.ajax('/api/v3/backup/'+data["id"],'GET',{}).done(function(data) {
                $("#backup-tables").find('option').remove();
                $("#backup-tables").append('<option value="">Choose..</option>');
                $.each(data.data,function(key, value)
                {
                    if(value>0){
                        $("#backup-tables").append('<option value=' + key + '><strong>' + key+'</strong> ('+value+' items)' + '</option>');
                    }
                });
                $('#backup-id').val(data['id'])
                $('#modalBackupInfo').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');
            });
        }
    });




$('#backup-tables').on('change', function (e) {
    var valueSelected = this.value;
    // var backup_id = +'/'+$('#backup-id').val()
    api.ajax('/api/v3/backup/table/'+valueSelected,'GET',{}).done(function(data) {
        if ( $.fn.dataTable.isDataTable( '#backup-table-detail' ) ) {
            backup_table_detail.clear().rows.add(data).draw()
        }else{
            backup_table_detail=$('#backup-table-detail').DataTable( {
                data: data,
                rowId: 'id',
                //~ language: {
                    //~ "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
                //~ },
                columns: [
                    { "data": "id", "width": "88px"},
                    { "data": "description", "width": "88px", "defaultContent": ""},
                    {
                    "className":      'actions-control',
                    "orderable":      false,
                    "data":           null,
                    "width": "88px",
                    "defaultContent": '<button class="btn btn-xs btn-individual-restore" type="button"  data-placement="top"><i class="fa fa-sign-in" style="color:darkgreen"></i></button>'
                    },
                    ],
                 "order": [[0, 'asc']],
                 "columnDefs": [ {
                                "targets": 2,
                                "render": function ( data, type, full, meta ) {
                                  if(full.new_backup_data){
                                      return '<button class="btn btn-xs btn-individual-restore" type="button"  data-placement="top"><i class="fa fa-sign-in" style="color:darkgreen"></i>New</button>';
                                  }else{
                                      return '<button class="btn btn-xs btn-individual-restore" type="button"  data-placement="top"><i class="fa fa-sign-in" style="color:darkgreen"></i>Exists</button>'
                                  }
                                }}]
            } );
        }
                        $('.btn-individual-restore').on('click', function (e){
                            data=backup_table_detail.row( $(this).parents('tr') ).data();
                            table=$('#backup-tables').val()
                            new PNotify({
                                    title: 'Restore data',
                                        text: "Do you really want to restore row "+data.id+" to table "+table+"?",
                                        hide: false,
                                        opacity: 0.9,
                                        confirm: {confirm: true},
                                        buttons: {closer: false,sticker: false},
                                        history: {history: false},
                                        addclass: 'pnotify-center'
                                    }).get().on('pnotify.confirm', function() {
                                        api.ajax('/api/v3/backup/restore/table/'+table,'PUT',{'data':data,}).done(function(data1) {
                                            api.ajax('/api/v3/backup/table/'+table,'GET',{}).done(function(data) {
                                                dtUpdateInsert(backup_table_detail,data,false);
                                            });
                                        });
                                    }).on('pnotify.cancel', function() {
                            });
                        });
    });
});

    // Maintenance
    maintenance_update_checkbox = (enabled) => {
        let status
        if (enabled) {
            status = 'check'
        } else {
            status = 'uncheck'
        }
        $('#maintenance_checkbox').iCheck(status)
    }
    maintenance_bind_checkbox = () => {
        $('#maintenance_checkbox').on('ifChecked', () => {
            maintenance_update_status(true)
        })
        $('#maintenance_checkbox').on('ifUnchecked', () => {
            maintenance_update_status(false)
        })
    }
    maintenance_update_status = (enabled) => {
        $('#maintenance_wrapper').hide()
        $('#maintenance_spinner').show()
        $('#maintenance_checkbox').unbind('ifChecked')
        $('#maintenance_checkbox').unbind('ifUnchecked')
        api.ajax(
            '/api/v3/maintenance',
            'PUT',
            enabled
        ).done((data) => {
            maintenance_update_checkbox(data)
            maintenance_bind_checkbox()
            $('#maintenance_spinner').hide()
            $('#maintenance_wrapper').show()
        })
    }
    api.ajax('/api/v3/maintenance', 'GET').done((data) => {
        maintenance_update_checkbox(data)
        maintenance_bind_checkbox()
        $('#maintenance_spinner').hide()
        $('#maintenance_wrapper').show()
    })
    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
})
function socketio_on(){
    socket.on('backups_data', function(data){
        var data = JSON.parse(data);
        dtUpdateInsert(backups_table,data,false);
    });

    socket.on('backups_deleted', function(data){
        var data = JSON.parse(data);
        backups_table.row('#'+data.id).remove().draw();
        new PNotify({
                title: "Backup deleted",
                text: "Backup "+data.name+" has been deleted",
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
        });
    });

    socket.on('scheduler_jobs_data', function(data){
        var data = JSON.parse(data);
        dtUpdateInsert(scheduler_table,data,false);
    });

    socket.on('scheduler_jobs_deleted', function(data){
        var data = JSON.parse(data);
        scheduler_table.row('#'+data.id).remove().draw();
        new PNotify({
                title: "Scheduler deleted",
                text: "Scheduler "+data.name+" has been deleted",
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
        });
    });

    socket.on ('result', function (data) {
        var data = JSON.parse(data);
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
    });

    socket.on('add_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $("#modalAddScheduler")[0].reset();
            $("#modalScheduler").modal('hide');
            //~ $('body').removeClass('modal-open');
            //~ $('.modal-backdrop').remove();
        }
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
    });
}

function scheduler_init(){
    $("#modalScheduler #modalAddScheduler").each(function () {
        this.reset();
      });

    $.ajax({
        type: 'GET',
        url: '/scheduler/actions',
    }).done(function(response) {
        response.forEach(function(action) {
            $("#modalScheduler #action").append(
              "<option value=" + action.id + ">" + action.name + "</option>"
            );
          })
    });

    $('#modalAddScheduler #kind').on('change', function (e) {
        var valueSelected = this.value;
        if(valueSelected == 'cron' || valueSelected == 'interval'){
            $('#modalAddScheduler #div_interval_cron').show()
            $('#modalAddScheduler #div_date').hide()
        }else if(valueSelected == 'date'){
            $('#modalAddScheduler #div_date').show()
            $('#modalAddScheduler #div_date #datePicker').daterangepicker({
                parentEl: "#modalAddScheduler #div_date",
                singleDatePicker: true,
                singleClasses: "picker_2",
                timePicker: true,
                locale: {
                    format: 'DD/MM/YYYY HH:mm'
                }
            })
            $('#modalAddScheduler #div_interval_cron').hide()
        }else{
            $('#modalAddScheduler #div_interval_cron').hide()
            $('#modalAddScheduler #div_date').hide()
        }
    })

    $('#modalAddScheduler #action').on('change', function (e) {
        var selectedAction = this.value;
        var selectedActionText = this.options[this.selectedIndex].text
        $.ajax({
            type: "GET",
            url: "/scheduler/action/"+selectedAction,
            contentType: "application/json",
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