let migrationTable = null;

$(document).ready(function() {
    renderMigrationDataTable();

    // Setup - add a text input to each footer cell
    $('#migration-table tfoot tr:first th').each(function () {
        var title = $(this).text();
        $(this).html('<input type="text" placeholder="Search ' + title + '" />');
    });

    // Apply the search
    migrationTable.columns().every(function () {
        var that = this;
        $( 'input', this.footer() ).on('keyup change', function () {
            if (that.search() !== this.value) {
                that
                    .search(this.value)
                    .draw();
            }
        });
    });

    $('tbody').on('click', 'button', function () {
        var row = migrationTable.row($(this).closest('tr'));
        var migrationId = row.data().id;

        if ($(this).hasClass('btn-revoke')) {
            new PNotify({
                title: 'Revoke Migration',
                text: 'Are you sure you want to change this migration status to <b>"revoked"</b>?\n\nThis action cannot be undone and the user may need to generate a <b>new migration token</b>.',
                icon: 'fa fa-question-circle',
                type: 'info',
                hide: false,
                confirm: {
                    confirm: true
                },
                buttons: {
                    closer: false,
                    sticker: false
                },
                history: {
                    history: false
                },
                addclass: "pnotify-center",
            }).get().on('pnotify.confirm', function() {
                $.ajax({
                    url: `/api/v3/admin/migrations/${migrationId}/revoke`,
                    type: 'PUT',
                    success: function() {
                        new PNotify({
                            title: `Migration revoked`,
                            text: `Migration status changed to <b>"revoked"</b>`,
                            type: 'success',
                            icon: 'fa fa-check',
                            hide: true,
                            delay: 5000,
                            opacity: 1,
                        })
                        migrationTable.ajax.reload();
                    },
                    error: function (data) {
                        new PNotify({
                            title: `ERROR revoking migration`,
                            text: data.responseJSON
                                ? data.responseJSON.description
                                : "Something went wrong",
                            type: "error",
                            hide: true,
                            icon: "fa fa-warning",
                            delay: 5000,
                            opacity: 1,
                        });
                    },
                });
            });
        }
    });

    $('#migration-table tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest("tr");
        var row = migrationTable.row(tr);
        if (row.child.isShown()) {
            row.child.hide();
            tr.removeClass("shown");
        } else {
            if (migrationTable.row('.shown').length) {
                $('.details-control', migrationTable.row('.shown').node()).click();
            }
            row.child(renderDeploymentDetailPannel(row.data())).show()
            tr.addClass('shown');
        }
    });
});

function renderDeploymentDetailPannel(d) {
    $newPanel = $migration_detail.clone();
    $newPanel.html(function (i, oldHtml) {
        return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description);
    });

    $newPanel.find("#desktops-migrated").text(d?.migrated_items?.desktops.length > 0 ? d.migrated_items.desktops.length : "-");
    $newPanel.find("#desktops-failed").html(d?.migrated_desktops === false ? '<i class="fa fa-circle" aria-hidden="true" style="color:red"></i>' : "");
    $newPanel.find("#desktops-detail").text("migrated_desktops_error" in d ? d.migrated_desktops_error : "");

    $newPanel.find("#templates-migrated").text(d?.migrated_items?.templates.length > 0 ? d.migrated_items.templates.length : "-");
    $newPanel.find("#templates-failed").html(d?.migrated_templates === false ? '<i class="fa fa-circle" aria-hidden="true" style="color:red"></i>' : "");
    $newPanel.find("#templates-detail").text("migrated_templates_error" in d ? d.migrated_templates_error : "");

    $newPanel.find("#media-migrated").text(d?.migrated_items?.media.length > 0 ? d.migrated_items.media.length : "-");
    $newPanel.find("#media-failed").html(d?.migrated_media === false ? '<i class="fa fa-circle" aria-hidden="true" style="color:red"></i>' : "");
    $newPanel.find("#media-detail").text("migrated_media_error" in d ? d.migrated_media_error : "");

    $newPanel.find("#deployments-migrated").text(d?.migrated_items?.deployments.length > 0 ? d.migrated_items.deployments.length : "-");
    $newPanel.find("#deployments-failed").html(d?.migrated_deployments === false ? '<i class="fa fa-circle" aria-hidden="true" style="color:red"></i>' : "");
    $newPanel.find("#deployments-detail").text("migrated_deployments_error" in d ? d.migrated_deployments_error : "");

    return $newPanel
}

function renderMigrationDataTable() {
    $migration_detail = $(".template-migration-detail");
    migrationTable = $(`#migration-table`).DataTable({
        "ajax": {
            "url": `/api/v3/admin/migrations`,
            "type": 'GET'
        },
        "sAjaxDataProp": "",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "searching": true,
        "paging": true,
        "footer": true,
        "order": [[4, 'desc']],
        "info": false,
        "deferRender": true,
        "columns": [
            {
                "className": 'details-control',
                "orderable": false,
                "data": null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button" data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "origin_username" },
            { "data": "target_username", "render": function (data, type, full, meta) {
                return data ? data : "-"; }
            },
            { "data": "category", "render": function (data, type, full, meta) {
                return data ? data : "-"; }
            },
            { "data": "status" },
            { "data": "created", "render": function (data, type, full, meta) {
                if (!data) { return "-"; }
                else if (type === 'display' || type === 'filter') { return renderMomentDate(data) }
                return data }
            },
            { "data": "import_time", "render": function (data, type, full, meta) {
                if (!data) { return "-"; }
                
                else if (type === 'display' || type === 'filter') { return renderMomentDate(data) }
                return data }
            },
            { "data": "migration_start_time", "render": function (data, type, full, meta) {
               if (!data) { return "-"; }
                else if (type === 'display' || type === 'filter') { return renderMomentDate(data) }
                return data }
            },
            { "data": "migration_end_time", "render": function (data, type, full, meta) {
               if (!data) { return "-"; }
                else if (type === 'display' || type === 'filter') { return renderMomentDate(data) }
                return data }
            },
            { "data": null, "render": function (data, type, full, meta) {
                if (["exported", "imported", "migrating"].includes(full.status)) {
                    return `<button title="Change the status to 'revoked'" class="btn btn-xs btn-danger btn-revoke"><i class="fa fa-times-circle"></i> Revoke</button>`;
                } else { return ""; } }
            }
        ]
    });
}

function renderMomentDate(timestamp) {
    let date = moment.unix(timestamp)
    return `<p title=${date.format('DD-MM-YYYY_HH:mm:ss')}>${date.fromNow()}<p>`
} 