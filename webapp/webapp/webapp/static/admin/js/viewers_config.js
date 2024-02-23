
$(document).ready(function () {
    const tableId = '#viewers-conf-table'
    const viewersConfTable = $(tableId).DataTable({
        ajax: {
            url: `/api/v3/admin/viewers-config`,
            contentType: 'application/json',
            type: 'GET',
        },
        sAjaxDataProp: '',
        language: {
            loadingRecords: '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        deferRender: true,
        columns: [
            {
                title: 'Viewer',
                data: 'viewer'
            },
            {
                title: 'Fixed',
                data: 'fixed',
                render: function (data, type, row, meta) {
                    return data.replaceAll("\n", "<br>")
                }
            },
            {
                title: 'Default',
                data: 'default',
                render: function (data, type, row, meta) {
                    return data.replaceAll("\n", "<br>")
                }
            },
            {
                title: 'Custom',
                data: 'custom',
                render: function (data, type, row, meta) {
                    return data.replaceAll("\n", "<br>")
                }
            },
            {
                render: function (data, type, row, meta) {
                    return `<button type="button" id="btn-edit" data-id="${row.key}" class="btn btn-xs btn-info btn-edit" title="Edit viewer options"><i class="fa fa-pencil"></i></button>
                    <button type="button" id="btn-reset" data-id="${row.key}" class="btn btn-xs btn-danger btn-reset" title="Reset values to default"><i class="fa fa-times"></i></button>`
                }
            }
        ]
    });

    $(tableId + " tbody").off('click').on('click', 'button', function () {
        let tr = $(this).closest("tr")
        let row = viewersConfTable.row(tr)
        switch ($(this).attr('id')) {
            case 'btn-edit':
                // $("#modalEditViewersConfig")[0].reset();
                $('#modalEditViewersConfig').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');
                $('#modalEditViewersConfig #custom').val(row.data().custom)
                $('#modalEditViewersConfig #viewer').val(row.data().key)
                break;
            case 'btn-reset':
                new PNotify({
                    title: "Confirm Change",
                    text: "The viewer custom options will be reset. Continue?",
                    hide: false,
                    type: 'info',
                    icon: 'fa fa-warning',
                    opacity: 0.9,
                    confirm: {
                        confirm: true,
                    },
                    buttons: {
                        closer: false,
                        sticker: false,
                    },
                    history: {
                        history: false,
                    },
                    addclass: "pnotify-center",
                })
                    .get()
                    .on("pnotify.confirm", function () {
                        $.ajax({
                            url: "/api/v3/admin/viewers-config/reset/" + row.data().key,
                            method: "PUT"
                        }).done(function (data) {
                            viewersConfTable.ajax.reload();
                            new PNotify({
                                title: "Viewer custom configuration reset successfully",
                                text: ``,
                                hide: true,
                                type: 'success',
                                opacity: 0.9,
                                addclass: "pnotify-center",
                            })
                        });
                    })
                break;
        }
    })

    $('#modalEditViewersConfig #send').off('click').on('click', function(e){
        var notice = new PNotify({
            text: 'Updating viewer custom options...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        data=$('#modalEditViewersConfig').serializeObject();
        $.ajax({
            url: "/api/v3/admin/viewers-config/" + $('#modalEditViewersConfig #viewer').val(),
            method: "PUT",
            contentType: 'application/json',
            data: JSON.stringify({
                "custom": $('#modalEditViewersConfig #custom').val()
            })
        }).done(function () {
            viewersConfTable.ajax.reload();
            $("#modalEditViewersConfigForm")[0].reset();
            $("#modalEditViewersConfig").modal('hide');
            notice.update({
                title: "Viewer custom configuration updated successfully",
                text: ``,
                hide: true,
                type: 'success',
                opacity: 0.9,
                icon: 'fa fa-check'
            })
        });
    });
})

