
$(document).ready(function () {

    $("#table-chart").DataTable({
        "ajax": {
            "url": "/api/v3/analytics/graph",
            "contentType": "application/json",
            "type": 'GET',
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "deferRender": true,
        "columns": [{ "data": "title" }, { "data": "subtitle" }, { "data": "grouping_name" }, { "data": "priority" }, { "data": "x_axis_days" },
            {
                "data": null, "render": function () {
                    return `
                        <button class="btn btn-xs btn-info btn-edit-graph" type="button" data-placement="top" ><i class="fa fa-pencil"></i></button>
                        <button class="btn btn-xs btn-danger btn-delete-graph" type="button" data-placement="top" ><i class="fa fa-times"></i></button>
                        `
                }
            }
        ],
    });

    populateGroupingSelect("#modalAnalyticsUsageGraph");

    $("#btn-graph_add").on("click", function () {
        renderGraphModal("add");
        $("#modalAnalyticsUsageGraph").modal({ backdrop: 'static', keyboard: false }).modal('show');
    });

    $('#modalAnalyticsUsageGraph').on('click', 'button#send', function () {
        if ($(this).data("action") == "add") {
            var form = $('#modalAnalyticsUsageGraphForm');
            data = form.serializeObject();
            delete data["id"];
            data.priority = parseInt(data.priority);
            data["x_axis_days"] = parseInt(data["x_axis_days"])

            form.parsley().validate();
            if (form.parsley().isValid()) {
                $.ajax({
                    url: "/api/v3/analytics/graph/",
                    type: 'POST',
                    data: JSON.stringify(data),
                    contentType: "application/json",
                }).then(function (groupings) {
                    new PNotify({
                        title: 'Added',
                        text: `Graph added successfully`,
                        hide: true,
                        delay: 2000,
                        opacity: 1,
                        type: 'success'
                    })
                    $("#table-chart").DataTable().ajax.reload().draw();
                    $('.modal').modal('hide');
                }).catch(function (data) {
                    new PNotify({
                        title: `ERROR adding graph`,
                        text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                });
            }
        } else if ($(this).data("action") == "edit") {
            var form = $('#modalAnalyticsUsageGraphForm');
            data = form.serializeObject();
            data.priority = parseInt(data.priority);
            data["x_axis_days"] = parseInt(data["x_axis_days"])

            form.parsley().validate();
            if (form.parsley().isValid()) {
                $.ajax({
                    url: "/api/v3/analytics/graph/" + data["id"],
                    type: 'PUT',
                    data: JSON.stringify(data),
                    contentType: "application/json",
                }).then(function (groupings) {
                    $('.modal').modal('hide');
                    new PNotify({
                        title: 'Updated',
                        text: `Graph updated successfully`,
                        hide: true,
                        delay: 2000,
                        opacity: 1,
                        type: 'success'
                    })
                    $("#table-chart").DataTable().ajax.reload().draw();
                }).catch(function (data) {
                    new PNotify({
                        title: `ERROR updating graph`,
                        text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                });
            }
        }
    });

    $('tbody').on('click', 'button', function () {
        var row = $(this).closest('table').DataTable().row($(this).closest('tr'));
        var id = row.data().id;

        if ($(this).hasClass('btn-delete-graph')) {
            new PNotify({
                title: 'Confirmation Needed',
                text: `Are you sure you want to delete this graph?`,
                hide: false,
                opacity: 0.9,
                confirm: {
                    confirm: true
                },
                buttons: {
                    closer: false,
                    sticker: false
                },
                addclass: 'pnotify-center'
            }).get().on('pnotify.confirm', function () {
                $.ajax({
                    type: 'DELETE',
                    url: "/api/v3/analytics/graph/" + id,
                    contentType: 'application/json',
                    success: function (data) {
                        new PNotify({
                            title: 'Deleted',
                            text: `${row.data().title} deleted successfully`,
                            hide: true,
                            delay: 2000,
                            opacity: 1,
                            type: 'success'
                        });
                        $("#table-chart").DataTable().ajax.reload().draw();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR deleting graph`,
                            text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        });
                    }
                })
            }).on('pnotify.cancel', function () {
            });
        } else if ($(this).hasClass('btn-edit-graph')) {
            renderGraphModal("edit");
            var modal = "#modalAnalyticsUsageGraph"
            $.ajax({
                type: 'GET',
                url: `/api/v3/analytics/graph/${id}`,
                contentType: 'application/json',
                success: function (data) {
                    $(modal + ' #id').val(id);
                    $(modal + ' #title').val(data.title);
                    $(modal + ' #subtitle').val(data.subtitle);
                    $(modal + ' #groupings').val(data.grouping);
                    $(modal + ' #priority').val(data.priority);
                    $(modal + ' #x_asix_days').val(data["x_axis_days"]);
                }
            });
            $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
        };
    });


});


function populateGroupingSelect(modal) {
    $.ajax({
        url: "/api/v3/admin/usage/groupings",
        type: "GET",
        contentType: "application/json"
    }).then(function (groupings) {
        $.each(groupings, function (key, value) {
            $(modal + " #groupings").append(`
                <option value="${value.id}">${value.name}</option>
            `);
        });
    });
}

function renderGraphModal(action) {
    var modal = "#modalAnalyticsUsageGraph";
    $(`${modal}Form`)[0].reset();

    if (action == "edit") {
        $(modal + " .modal-header h4").html('<i class="fa fa-pencil fa-1x"></i> <i class="fa fa-bar-chart"></i> Edit Analytics Graph');
        $(modal + " .modal-footer #send").html("Edit Graph").data("action", action);

    } else if (action == "add") {
        $(modal + " .modal-header h4").html('<i class="fa fa-plus fa-1x"></i> <i class="fa fa-bar-chart"></i> Add Analytics Graph');
        $(modal + " .modal-footer #send").html("Add Graph").data("action", action);
    }
}
