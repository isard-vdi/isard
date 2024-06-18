/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function () {
    $template_role = $(".template-detail-roles");
    var table = $('#roles').DataTable({
        "ajax": {
            "url": "/admin/roles",
            "dataSrc": "",
            "type": "GET",
        },
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "columns": [
            {
                "className": 'details-control',
                "orderable": false,
                "data": null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "id", className: "xe-id" },
            { "data": "name", className: "xe-name" },
            { "data": "description", className: "xe-description" }
        ]
    });

    $('#roles').find('tbody').on('click', 'td.details-control', function () {
        console.log('roles click');
        var tr = $(this).closest('tr');
        var row = table.row(tr);

        if (row.child.isShown()) {
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            row.child(renderRolesDetailPannel(row.data())).show();
            actionsRolDetail()

            tr.addClass('shown');
        }
    });

    // Hide details for managers
    if ($('meta[id=user_data]').attr('data-role') != 'admin') {
        table.column(0).visible(false);
    }
});

function renderRolesDetailPannel(d) {
    console.log('d', d);
    $newPanel = $template_role.clone();
    console.log('newPanel', $newPanel);
    $newPanel.html(function (i, oldHtml) {
        return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description);
    });
    console.log('newPanel', $newPanel);
    return $newPanel
}


function actionsRolDetail() {
    $('.btn-edit-role').off('click').on('click', function () {
        $('#modalEditRole').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        var pk = $(this).closest("div").attr("data-pk");
        console.log('this', $(this).closest("div"));
        console.log('pk', pk);
        $("#modalEditRoleForm")[0].reset();


        $.ajax({
            type: "GET",
            url: "/api/v3/admin/role/" + pk,
            contentType: "application/json",
            success: function (role) {
                $('#modalEditRoleForm #id').val(pk);
                $('#modalEditRoleForm #name').val(role.name);
                $('#modalEditRoleForm #description').val(role.description);
            }
        });

        $("#modalEditRole #send").off('click').on('click', function (e) {
            var form = $('#modalEditRoleForm');
            form.parsley().validate();
            if (form.parsley().isValid()) {
                data = form.serializeObject();
                var notice = new PNotify({
                    text: 'Updating role...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: "PUT",
                    url: "/api/v3/admin/role/" + data['id'],
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function (data) {
                        notice.update({
                            title: 'Updated',
                            text: 'Role updated successfully',
                            hide: true,
                            delay: 1000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                        $('form').each(function () { this.reset() });
                        $('.modal').modal('hide');
                    },
                    error: function (data) {
                        notice.update({
                            title: 'ERROR updating role' + data.id,
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 2000,
                            opacity: 1
                        })
                    }
                });
            }
        });
    });
}